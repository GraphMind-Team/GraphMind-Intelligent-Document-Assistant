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

# Free-tier-friendly default -- overridable via OPENROUTER_MODEL for local
# testing against a different model without a code change.
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

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
_MAX_ATTEMPTS = 2
_TIMEOUT_SECONDS = 30.0

# Retrying a transient provider failure in the same microsecond mostly
# just re-hits whatever is still failing, spending the second attempt for
# nothing. A short fixed pause (not exponential backoff -- there's only
# ever one retry) makes the budget mean something. Safe to sleep here:
# `ingest_document` runs this in Starlette's background threadpool, off
# the event loop, with no user waiting synchronously on the response.
_RETRY_DELAY_SECONDS = 2.0

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
    """Internal: a transport-level failure (timeout/5xx) or a malformed
    response (bad JSON, wrong shape) -- both get the same 2-attempt retry
    budget as the Design Notes specify, rather than distinguishing "the
    network failed" from "the model responded with garbage"."""


def extract_entities_and_relationships(text: str) -> ExtractionResult:
    """One document's concatenated chapter text -> validated entities and
    relationships.

    Retries up to `_MAX_ATTEMPTS` total on a timeout, a 5xx response, or a
    malformed/unparseable response body (bad JSON, or JSON that isn't the
    expected `{"entities": [...], "relationships": [...]}` shape) --
    a malformed response is treated exactly like a transport error, not a
    crash, per the Design Notes. A 4xx response (bad request, bad API key)
    is not retryable and raises immediately -- retrying a request that's
    wrong by construction just burns the attempt budget for no chance of a
    different outcome.

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
                time.sleep(_RETRY_DELAY_SECONDS)
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
    # A 4xx here is not retryable -- wrapped in `ExtractionError` (not the
    # raw `httpx.HTTPStatusError`) so this function keeps the promise its
    # own docstring makes: callers never see the underlying httpx/json
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
