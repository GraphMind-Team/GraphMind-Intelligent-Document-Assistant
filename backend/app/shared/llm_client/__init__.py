"""Shared LLM-client wrapper (Story 2.4, first real implementation).

Per architecture decision AD-6, this package is the sole path to
OpenRouter -- `documents/service.py` (and any future caller) must never
construct an OpenRouter/OpenAI SDK client, or issue an HTTP call to
OpenRouter, directly.

Only one capability exists today: `extract_entities_and_relationships`,
which turns a document's concatenated chapter text into entities and
relationships constrained to OD-1's closed type sets. This module has no
concept of a user-facing conversation, and deliberately never will --
chat/refusal-short-circuit logic is Epic 3's later addition to this same
package, not something this story's extraction call needs or should grow.

Retry mirrors `shared/embeddings/model.py` and `shared/data_access/
weaviate_client.py`'s treatment of transient provider failures: a fixed,
small attempt budget (`_MAX_ATTEMPTS`), not exponential backoff/jitter --
this call runs inside a background ingestion task with no user waiting
synchronously, so a bounded retry that fails fast into `Failed` (Story
2.3's precedent) is preferred over a longer retry loop that would just
delay reaching that same terminal state.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field

import httpx

from app.shared.data_access.shapes import WeaviateSearchResult

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free-tier default -- overridable via OPENROUTER_MODEL without a code
# change, which is the intended fix if this slug stops being offered free
# (see below) rather than editing this line under time pressure.
#
# Chosen by measuring candidates from OpenRouter's live free-tier list
# against this module's actual prompt: it returned correctly-shaped,
# correctly-typed entities *and* relationships for English and Bulgarian
# (this project supports Bulgarian documents -- see the multilingual
# embedding model in `shared/embeddings/`), and was the fastest of the
# candidates that did. Rejected: `meta-llama/llama-3.3-70b-instruct:free`,
# the previous default, which now 404s with "unavailable for free";
# `openrouter/free`, which returned `entities` as bare strings instead of
# objects, so every entity was dropped by `_parse_and_validate` and its
# relationships then had nothing to resolve against.
#
# Free slugs are not a stable contract -- they get withdrawn, as the
# previous default did. A 404 here is (correctly) non-retryable and fails
# the document, so the symptom is loud rather than silent.
DEFAULT_MODEL = "openai/gpt-oss-20b:free"

# OD-1's closed type sets (resolved by the human before this spec was
# written -- see the spec's Intent section). The prompt below asks the
# model to only ever emit these, but that's advisory: `_parse_and_validate`
# enforces this in code after every call, because an LLM response is never
# trusted from the prompt alone.
ENTITY_TYPES = frozenset({"Person", "Organization", "Project", "Product", "Location"})
RELATIONSHIP_TYPES = frozenset({"WORKS_AT", "SUPPLIES", "PART_OF", "LOCATED_IN", "RELATED_TO"})

# 2 attempts total (not 2 retries) -- matches `weaviate_client`/
# `embeddings`'s framing of "retryable" as "transient provider failure",
# not an open-ended retry loop.
# 3 attempts, not the 2 this story's Design Notes first specified: free-tier
# 429s are routine rather than exceptional (see
# `extract_entities_and_relationships`), and a single retry against a
# provider that rate-limits in bursts fails documents that would have
# succeeded moments later.
_MAX_ATTEMPTS = 3

# Generous, and deliberately so. Measured against the real provider: even a
# one-sentence prompt took ~32s end to end, and real ingestion sends up to
# EXTRACTION_CHAR_BUDGET (12,000) characters. httpx's `timeout=` is
# per-operation (connect/read/write), not total elapsed, so this is a
# floor on patience rather than a wall-clock cap -- but at 30s it was close
# enough to observed latency to start failing healthy requests.
_TIMEOUT_SECONDS = 120.0

# Retrying a transient failure in the same microsecond mostly re-hits
# whatever is still failing, spending the attempt for nothing. Doubles per
# attempt, and a 429's own `Retry-After` overrides it entirely. Safe to
# sleep here: `ingest_document` runs this in Starlette's background
# threadpool, off the event loop, with no user waiting synchronously.
_RETRY_DELAY_SECONDS = 3.0
_MAX_RETRY_DELAY_SECONDS = 30.0

# Timeout/retry budget for chat-answer generation (Story 3.1) -- deliberately
# different numbers from extraction's above, not a copy-paste. Extraction runs
# in a background ingestion task with no user waiting synchronously, hence its
# generous 120s/3-attempt budget. A chat answer is requested synchronously by
# a waiting user, which argues for a *tighter* budget -- but DEFAULT_MODEL's
# own docstring below records that this same free-tier model took ~32s even
# for a short prompt. An aggressively tight timeout tuned only against NFR-1's
# 8s p95 target would make the happy path fail almost every time (retry then
# 503), which defeats the point of this story. 45s/attempt is chosen against
# that measured reality instead: generous enough for a real call to actually
# complete, still bounded (2 attempts, retry delay capped at
# _MAX_RETRY_DELAY_SECONDS above) rather than open-ended. NFR-1 (p95 < 8s) is
# knowingly NOT met by this configuration -- worst case across both attempts
# is ~120s (45s + up to 30s of a 429's own Retry-After + 45s). The real fix is
# a faster model via OPENROUTER_CHAT_MODEL below, once one is chosen; this
# story documents the deviation rather than pretending a tighter number would
# have solved it.
_CHAT_TIMEOUT_SECONDS = 45.0
_CHAT_MAX_ATTEMPTS = 2
_CHAT_RETRY_DELAY_SECONDS = 3.0

# Budgets ONLY the assembled passage block handed to the model -- not the
# surrounding instruction/numbering scaffolding, and not the question itself
# (bounded separately by chat/schemas.py's AskRequest.max_length=2000). Both
# sit on top of this budget as unaccounted-for reserve; a future increase to
# that max_length should revisit this number too, since together they bound
# the effective prompt size sent to the free 20b model's context window.
# Passages are dropped wholesale from the tail of the (already
# nearest-first-ordered) list once the next one wouldn't fit -- never
# truncated mid-passage, since a half-sentence passage is worse context than
# one fewer whole passage.
_MAX_PROMPT_CHARS = 6000

_SYSTEM_PROMPT = (
    "You extract entities and relationships from a document's text for a "
    "knowledge graph. Respond with strict JSON only -- no prose, no markdown "
    "code fences -- matching exactly this shape: "
    '{"entities": [{"name": "...", "type": "..."}], '
    '"relationships": [{"source": "...", "target": "...", "type": "..."}]}. '
    f"Every entity \"type\" must be exactly one of: {', '.join(sorted(ENTITY_TYPES))}. "
    f"Every relationship \"type\" must be exactly one of: {', '.join(sorted(RELATIONSHIP_TYPES))} "
    "-- use RELATED_TO if nothing else fits. \"source\" and \"target\" must each match "
    "an entity's \"name\" exactly. If nothing in the text qualifies, respond with "
    '{"entities": [], "relationships": []} -- an empty result is a valid answer, not an error.'
)


@dataclass(frozen=True)
class ExtractedEntity:
    """One entity as parsed from the LLM's JSON response, already
    validated against `ENTITY_TYPES` -- never an out-of-vocabulary type."""

    name: str
    type: str


@dataclass(frozen=True)
class ExtractedRelationship:
    """One relationship as parsed from the LLM's JSON response, already
    validated against `RELATIONSHIP_TYPES`. `source`/`target` are entity
    names (matched against `ExtractedEntity.name`, not validated against
    each other here -- a relationship naming an entity the model didn't
    also return as an entity is the caller's concern, not this module's)."""

    source: str
    target: str
    type: str


@dataclass(frozen=True)
class ExtractionResult:
    """Return shape of `extract_entities_and_relationships`. An empty
    result (`entities=[]`, `relationships=[]`) is a valid outcome -- "no
    notable entities" is not a failure (the story's I/O matrix)."""

    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)


class ExtractionError(Exception):
    """Raised when OpenRouter can't be reached, or returns a malformed/
    unparseable response, after every retry attempt is exhausted -- or
    immediately for a non-retryable failure (e.g. a 4xx from a bad API
    key/request, or missing configuration). The caller (`documents/
    service.py`) catches this the same as any other Graphing-step failure
    and runs the AD-1 rollback; it never needs to inspect this
    exception's type."""


class _RetryableExtractionError(Exception):
    """Internal: a transport-level failure (timeout/5xx), a rate limit
    (429), or a malformed response (bad JSON, wrong shape) -- all get the
    same retry budget, rather than distinguishing "the network failed"
    from "the model responded with garbage".

    `retry_after` carries the server's own `Retry-After` hint in seconds
    when it sent one, so a 429 waits as long as the provider actually
    asked for instead of a fixed guess.
    """

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(response: httpx.Response) -> float | None:
    """`Retry-After` in delta-seconds form, when present and sane.

    Only the numeric form is honoured -- the HTTP-date form is legal but
    OpenRouter doesn't send it, and a misparsed date would be worse than
    falling back to the fixed delay. Capped so a provider advertising a
    multi-minute cooldown can't pin a background ingestion task open far
    longer than the caller's own patience.
    """
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:
        return None
    if seconds <= 0:
        return None
    return min(seconds, _MAX_RETRY_DELAY_SECONDS)


def extract_entities_and_relationships(text: str) -> ExtractionResult:
    """One document's concatenated chapter text -> validated entities and
    relationships.

    Retries up to `_MAX_ATTEMPTS` total on a timeout, a 5xx response, a
    429 rate limit, or a malformed/unparseable response body (bad JSON, or
    JSON that isn't the expected `{"entities": [...], "relationships":
    [...]}` shape) -- a malformed response is treated exactly like a
    transport error, not a crash, per the Design Notes.

    429 is retryable despite being a 4xx, and that distinction is load-
    bearing rather than pedantic: this project runs on OpenRouter's free
    tier by hard constraint, where "temporarily rate-limited upstream,
    please retry shortly" is a routine response, not a broken request.
    Lumping it in with the genuinely non-retryable 4xx (bad API key,
    malformed request) would fail documents for a condition that clears on
    its own seconds later. Every *other* 4xx still raises immediately --
    retrying a request that's wrong by construction just burns the budget
    for no chance of a different outcome.

    Backoff grows between attempts, and a 429 carrying a `Retry-After`
    waits exactly as long as the provider asked instead of guessing.

    Raises `ExtractionError` once attempts are exhausted (or immediately,
    for a non-retryable failure) -- callers never see the underlying
    `httpx`/`json` exception directly.
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            content = _call_openrouter(text)
            return _parse_and_validate(content)
        except _RetryableExtractionError as exc:
            last_error = exc
            logger.warning(
                "extract_entities_and_relationships: attempt %s/%s failed: %s",
                attempt,
                _MAX_ATTEMPTS,
                exc,
            )
            if attempt < _MAX_ATTEMPTS:
                # The provider's own hint wins over the local schedule --
                # it knows when its limit resets and we don't.
                delay = exc.retry_after
                if delay is None:
                    delay = min(
                        _RETRY_DELAY_SECONDS * (2 ** (attempt - 1)),
                        _MAX_RETRY_DELAY_SECONDS,
                    )
                logger.info("Retrying entity extraction in %.1fs", delay)
                time.sleep(delay)
    raise ExtractionError(
        f"OpenRouter entity extraction failed after {_MAX_ATTEMPTS} attempts"
    ) from last_error


def _call_openrouter(text: str) -> str:
    """Issues the chat-completion call and returns the raw message content
    (a string the caller still has to JSON-parse) -- not parsed here, so
    `extract_entities_and_relationships`'s retry loop can treat "the
    network failed" and "the response body was garbage" uniformly via the
    same `_RetryableExtractionError`."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing required environment variable: OPENROUTER_API_KEY. "
            "See backend/.env.example."
        )
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise _RetryableExtractionError(f"OpenRouter request timed out: {exc}") from exc
    except httpx.TransportError as exc:
        raise _RetryableExtractionError(f"OpenRouter request failed: {exc}") from exc

    if response.status_code >= 500:
        raise _RetryableExtractionError(
            f"OpenRouter returned {response.status_code}: {response.text[:500]}"
        )
    # 429 is a 4xx but is explicitly transient -- on the free tier this is
    # the single most common failure, and it clears by itself. Retried,
    # honouring the server's own `Retry-After` when it sent one.
    if response.status_code == 429:
        raise _RetryableExtractionError(
            f"OpenRouter rate-limited the request (429): {response.text[:500]}",
            retry_after=_parse_retry_after(response),
        )
    # Every other 4xx is not retryable -- wrapped in `ExtractionError` (not
    # the raw `httpx.HTTPStatusError`) so this function keeps the promise
    # its own docstring makes: callers never see the underlying httpx/json
    # exception directly, on any failure path. Raised immediately, not via
    # `_RetryableExtractionError`, so it propagates straight out on the
    # first attempt rather than being caught by the retry loop.
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ExtractionError(
            f"OpenRouter returned a non-retryable {response.status_code}: {response.text[:500]}"
        ) from exc

    try:
        body = response.json()
        return body["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise _RetryableExtractionError(
            f"OpenRouter response missing choices[0].message.content: {exc}"
        ) from exc


def _parse_and_validate(content: str) -> ExtractionResult:
    """Parses the model's JSON string and drops anything outside OD-1's
    closed type sets -- the enforcement point the story's Boundaries
    require ("validate the LLM's response against those sets IN CODE
    after the call returns... never trust the prompt alone"). An
    out-of-vocabulary type is dropped with a warning log, one entity/
    relationship at a time; it never fails the whole extraction, let alone
    the document."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise _RetryableExtractionError(f"OpenRouter returned malformed JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise _RetryableExtractionError("OpenRouter JSON response was not a JSON object")

    raw_entities = payload.get("entities", [])
    raw_relationships = payload.get("relationships", [])
    if not isinstance(raw_entities, list) or not isinstance(raw_relationships, list):
        raise _RetryableExtractionError(
            "OpenRouter JSON response's entities/relationships were not lists"
        )

    entities: list[ExtractedEntity] = []
    for item in raw_entities:
        if not isinstance(item, dict):
            logger.warning("Dropping malformed entity entry (not an object): %r", item)
            continue
        name = item.get("name")
        entity_type = item.get("type")
        if not isinstance(name, str) or not name.strip():
            logger.warning("Dropping entity with missing/blank name: %r", item)
            continue
        if entity_type not in ENTITY_TYPES:
            logger.warning(
                "Dropping entity %r: out-of-vocabulary type %r (allowed: %s)",
                name,
                entity_type,
                sorted(ENTITY_TYPES),
            )
            continue
        entities.append(ExtractedEntity(name=name.strip(), type=entity_type))

    relationships: list[ExtractedRelationship] = []
    for item in raw_relationships:
        if not isinstance(item, dict):
            logger.warning("Dropping malformed relationship entry (not an object): %r", item)
            continue
        source = item.get("source")
        target = item.get("target")
        relationship_type = item.get("type")
        if not isinstance(source, str) or not source.strip() or not isinstance(target, str) or not target.strip():
            logger.warning("Dropping relationship with missing/blank source or target: %r", item)
            continue
        if relationship_type not in RELATIONSHIP_TYPES:
            logger.warning(
                "Dropping relationship %r -> %r: out-of-vocabulary type %r (allowed: %s)",
                source,
                target,
                relationship_type,
                sorted(RELATIONSHIP_TYPES),
            )
            continue
        relationships.append(
            ExtractedRelationship(source=source.strip(), target=target.strip(), type=relationship_type)
        )

    return ExtractionResult(entities=entities, relationships=relationships)


# ---------------------------------------------------------------------------
# Chat-answer generation (Story 3.1) -- this module's own docstring above
# anticipated this addition living here ("chat/refusal-short-circuit logic
# is Epic 3's later addition to this same package"). Kept in the same file
# as extraction rather than split into a submodule: the addition is small
# enough (one public function, one exception type, a prompt builder, a
# parse/validate helper) that a split isn't yet earning its keep.
# ---------------------------------------------------------------------------

_CHAT_SYSTEM_PROMPT_TEMPLATE = (
    "You answer a question using ONLY the numbered passages below. Respond "
    "with strict JSON only -- no prose, no markdown code fences -- matching "
    'exactly this shape: {{"segments": [{{"text": "...", "passage_numbers": '
    '[1, 2]}}]}}. Each "text" is one claim-bearing sentence or clause of your '
    "answer. Every segment's \"passage_numbers\" must list every passage (by "
    "its number below) that supports that segment's claim -- never leave "
    "this list empty for a claim-bearing segment. Use only information "
    "present in the passages; do not invent facts. If the passages do not "
    'support any answer at all, respond with {{"segments": []}}.\n\n{passages}'
)


@dataclass(frozen=True)
class AnswerSegment:
    """One piece of a generated chat answer, as parsed from the LLM's JSON
    response and already validated against the passages it was given --
    never an out-of-range passage reference, and never a claim-bearing
    segment left without at least one valid citation (this is where FR-9/
    the story's AC6 guarantee is actually enforced, in code, not just in
    the prompt)."""

    text: str
    passage_numbers: list[int]  # 1-based, indexes into the passages `generate_answer` was called with


@dataclass(frozen=True)
class AnswerResult:
    """Return shape of `generate_answer`. An empty result (`segments=[]`)
    is a valid, non-error outcome -- the model finding nothing in the
    given passages worth answering with mirrors `ExtractionResult`'s "no
    notable entities" precedent, not a failure this function should raise
    for."""

    segments: list[AnswerSegment] = field(default_factory=list)


class ChatCompletionError(Exception):
    """Raised when OpenRouter can't be reached, times out, or returns a
    malformed/unparseable response to a chat-answer request, after the
    retry budget is exhausted -- or immediately for a non-retryable
    failure. Distinct from `ExtractionError`: `chat/service.py` catches
    ONLY this exception and turns it into `HTTPException(503, ...)` per
    AD-3/AD-6 -- the two call sites (background document ingestion vs.
    synchronous live chat) must never be conflated by a shared except
    clause, since a 503 belongs only to the synchronous chat path.

    `generate_answer` is only ever called with at least one passage
    (`chat/service.py`'s own responsibility, enforced before this
    function is ever reached) -- so this exception can never mean "there
    was nothing to answer from"; that's a distinct, earlier branch in the
    service layer, never this wrapper's concern."""


class _RetryableChatError(Exception):
    """Internal: mirrors `_RetryableExtractionError`'s triggers exactly
    (a transport-level failure, a 429 rate limit, or a malformed/wrong-
    shape response), but is a separate class -- a future change to
    extraction's retry semantics must never silently affect chat's
    independently-tuned budget via a shared base class."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _select_passages_within_budget(passages: list[WeaviateSearchResult]) -> list[WeaviateSearchResult]:
    """Passages that fit inside `_MAX_PROMPT_CHARS`, preserving the
    caller's (nearest-first) order. Drops whole passages from the tail
    once the next one wouldn't fit -- see `_MAX_PROMPT_CHARS`'s own
    comment for why this never truncates a passage's text mid-way."""
    selected: list[WeaviateSearchResult] = []
    used_chars = 0
    for index, passage in enumerate(passages, start=1):
        line_len = len(f"Passage {index} (Chapter: {passage.chapter}): {passage.text}\n")
        if used_chars + line_len > _MAX_PROMPT_CHARS:
            break
        selected.append(passage)
        used_chars += line_len
    return selected


def _build_chat_system_prompt(passages: list[WeaviateSearchResult]) -> str:
    passage_block = "\n".join(
        f"Passage {index} (Chapter: {passage.chapter}): {passage.text}"
        for index, passage in enumerate(passages, start=1)
    )
    return _CHAT_SYSTEM_PROMPT_TEMPLATE.format(passages=passage_block)


def generate_answer(question: str, passages: list[WeaviateSearchResult]) -> AnswerResult:
    """A question plus its retrieved passages -> a structured, citable
    answer. Callers (`chat/service.py`) must only call this with a
    non-empty `passages` list -- an empty-library/no-retrieval-results
    case is that caller's own degenerate branch, never this function's.

    Retries up to `_CHAT_MAX_ATTEMPTS` total on a timeout, a 5xx, a 429,
    or a malformed/unparseable response -- the same treatment
    `extract_entities_and_relationships` gives those conditions, on a
    much tighter, chat-appropriate budget (see `_CHAT_TIMEOUT_SECONDS`'s
    comment for why the numbers differ). A 429's own `Retry-After` header
    overrides the local backoff schedule, same as extraction.

    Raises `ChatCompletionError` once attempts are exhausted (or
    immediately for a non-retryable failure) -- callers never see the
    underlying `httpx`/`json` exception directly.
    """
    included_passages = _select_passages_within_budget(passages)
    system_prompt = _build_chat_system_prompt(included_passages)

    last_error: Exception | None = None
    for attempt in range(1, _CHAT_MAX_ATTEMPTS + 1):
        try:
            content = _call_openrouter_for_chat(system_prompt, question)
            return _parse_and_validate_answer(content, len(included_passages))
        except _RetryableChatError as exc:
            last_error = exc
            logger.warning(
                "generate_answer: attempt %s/%s failed: %s", attempt, _CHAT_MAX_ATTEMPTS, exc
            )
            if attempt < _CHAT_MAX_ATTEMPTS:
                delay = exc.retry_after
                if delay is None:
                    delay = min(
                        _CHAT_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)),
                        _MAX_RETRY_DELAY_SECONDS,
                    )
                logger.info("Retrying chat generation in %.1fs", delay)
                time.sleep(delay)
    raise ChatCompletionError(
        f"OpenRouter chat generation failed after {_CHAT_MAX_ATTEMPTS} attempts"
    ) from last_error


def _call_openrouter_for_chat(system_prompt: str, question: str) -> str:
    """Issues the chat-completion call for a generated answer and returns
    the raw message content -- not parsed here, mirrors `_call_openrouter`'s
    split so the retry loop can treat "the network failed" and "the
    response body was garbage" uniformly via `_RetryableChatError`."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing required environment variable: OPENROUTER_API_KEY. "
            "See backend/.env.example."
        )
    # Independent of OPENROUTER_MODEL (extraction's own override, above) --
    # lets a faster model be swapped in for chat generation later purely via
    # configuration, without touching extraction's separately-tuned choice.
    model = os.environ.get("OPENROUTER_CHAT_MODEL", DEFAULT_MODEL)

    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=_CHAT_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise _RetryableChatError(f"OpenRouter chat request timed out: {exc}") from exc
    except httpx.TransportError as exc:
        raise _RetryableChatError(f"OpenRouter chat request failed: {exc}") from exc

    if response.status_code >= 500:
        raise _RetryableChatError(
            f"OpenRouter returned {response.status_code}: {response.text[:500]}"
        )
    # 429 is retried and honors Retry-After, same reasoning as extraction's
    # own handling above -- free-tier rate-limiting is the more likely
    # failure mode here than a genuine 5xx/timeout.
    if response.status_code == 429:
        raise _RetryableChatError(
            f"OpenRouter rate-limited the chat request (429): {response.text[:500]}",
            retry_after=_parse_retry_after(response),
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ChatCompletionError(
            f"OpenRouter returned a non-retryable {response.status_code}: {response.text[:500]}"
        ) from exc

    try:
        body = response.json()
        return body["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise _RetryableChatError(
            f"OpenRouter chat response missing choices[0].message.content: {exc}"
        ) from exc


def _parse_and_validate_answer(content: str, passage_count: int) -> AnswerResult:
    """Parses the model's JSON string and enforces, in code, that every
    segment reaching the caller carries at least one valid citation --
    never trusting the prompt's own instruction alone to hold (mirrors
    `_parse_and_validate`'s OD-1 enforcement for extraction). An
    out-of-range `passage_numbers` entry is dropped individually
    (logged); a segment left with zero valid numbers after filtering is
    dropped entirely -- an uncited claim-bearing sentence must never
    reach the frontend, since that's exactly the guarantee FR-9/AC6
    require. `{"segments": []}` is a valid, non-error outcome (mirrors
    extraction's "empty is not a failure")."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise _RetryableChatError(f"OpenRouter returned malformed JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise _RetryableChatError("OpenRouter JSON response was not a JSON object")

    raw_segments = payload.get("segments", [])
    if not isinstance(raw_segments, list):
        raise _RetryableChatError("OpenRouter JSON response's segments was not a list")

    segments: list[AnswerSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            logger.warning("Dropping malformed answer segment (not an object): %r", item)
            continue
        text = item.get("text")
        raw_numbers = item.get("passage_numbers", [])
        if not isinstance(text, str) or not text.strip():
            logger.warning("Dropping answer segment with missing/blank text: %r", item)
            continue
        if not isinstance(raw_numbers, list):
            logger.warning("Dropping answer segment with non-list passage_numbers: %r", item)
            continue

        valid_numbers = [
            n
            for n in raw_numbers
            if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= passage_count
        ]
        invalid_numbers = [n for n in raw_numbers if n not in valid_numbers]
        if invalid_numbers:
            logger.warning(
                "Dropping out-of-range passage_numbers %r from answer segment %r "
                "(valid range: 1-%s)",
                invalid_numbers,
                text,
                passage_count,
            )
        if not valid_numbers:
            logger.warning("Dropping answer segment with no valid citations: %r", item)
            continue

        segments.append(AnswerSegment(text=text.strip(), passage_numbers=valid_numbers))

    return AnswerResult(segments=segments)
