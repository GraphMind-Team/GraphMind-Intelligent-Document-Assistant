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
