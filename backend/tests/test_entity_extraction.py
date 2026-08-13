"""`shared/llm_client` tests (Story 2.4): OD-1 closed-type-set validation
(out-of-vocabulary entities/relationships dropped, not fatal), the "no
notable entities" empty-result outcome, the 2-attempt retry budget on
timeout/5xx/malformed JSON, and that a non-retryable 4xx fails immediately
without burning a second attempt. All isolated from a real OpenRouter call
via mocking `httpx.post`, mirroring `test_weaviate_client.py`'s approach to
the Weaviate SDK.
"""

import json

import httpx
import pytest

from app.shared import llm_client as llm_client_module
from app.shared.llm_client import (
    ExtractionError,
    ExtractionResult,
    extract_entities_and_relationships,
)

_REQUEST = httpx.Request("POST", llm_client_module.OPENROUTER_URL)


def _openrouter_response(status_code: int, *, content: str | None = None, body: dict | None = None):
    """Builds a real `httpx.Response` (not a bare mock) so `raise_for_status`
    behaves exactly as it would against a real OpenRouter reply."""
    if body is None:
        body = {"choices": [{"message": {"content": content}}]}
    return httpx.Response(status_code, json=body, request=_REQUEST)


@pytest.fixture(autouse=True)
def _openrouter_api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def _valid_content():
    return json.dumps(
        {
            "entities": [
                {"name": "Maria Ivanova", "type": "Person"},
                {"name": "TechCorp", "type": "Organization"},
            ],
            "relationships": [
                {"source": "Maria Ivanova", "target": "TechCorp", "type": "WORKS_AT"},
            ],
        }
    )


def test_extract_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        extract_entities_and_relationships("some document text")


def test_extract_returns_entities_and_relationships_on_success(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=_valid_content())
    )

    result = extract_entities_and_relationships("Maria Ivanova works at TechCorp.")

    assert isinstance(result, ExtractionResult)
    assert [(e.name, e.type) for e in result.entities] == [
        ("Maria Ivanova", "Person"),
        ("TechCorp", "Organization"),
    ]
    assert [(r.source, r.target, r.type) for r in result.relationships] == [
        ("Maria Ivanova", "TechCorp", "WORKS_AT")
    ]


def test_extract_empty_result_is_a_valid_outcome_not_an_error(monkeypatch):
    empty_content = json.dumps({"entities": [], "relationships": []})
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=empty_content)
    )

    result = extract_entities_and_relationships("A document with nothing notable in it.")

    assert result.entities == []
    assert result.relationships == []


def test_extract_drops_out_of_vocabulary_entity_type_but_keeps_the_rest(monkeypatch, caplog):
    content = json.dumps(
        {
            "entities": [
                {"name": "Maria Ivanova", "type": "Person"},
                {"name": "Annual Conference", "type": "Event"},  # not in OD-1's set
            ],
            "relationships": [],
        }
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    with caplog.at_level("WARNING"):
        result = extract_entities_and_relationships("text")

    assert [e.name for e in result.entities] == ["Maria Ivanova"]
    assert "out-of-vocabulary" in caplog.text
    assert "Event" in caplog.text


def test_extract_drops_out_of_vocabulary_relationship_type_but_keeps_the_rest(monkeypatch, caplog):
    content = json.dumps(
        {
            "entities": [
                {"name": "Maria Ivanova", "type": "Person"},
                {"name": "TechCorp", "type": "Organization"},
            ],
            "relationships": [
                {"source": "Maria Ivanova", "target": "TechCorp", "type": "WORKS_AT"},
                {"source": "Maria Ivanova", "target": "TechCorp", "type": "MANAGES"},  # not in OD-1's set
            ],
        }
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    with caplog.at_level("WARNING"):
        result = extract_entities_and_relationships("text")

    assert [r.type for r in result.relationships] == ["WORKS_AT"]
    assert "out-of-vocabulary" in caplog.text
    assert "MANAGES" in caplog.text


def test_extract_drops_entries_missing_required_fields(monkeypatch):
    content = json.dumps(
        {
            "entities": [{"name": "", "type": "Person"}, {"type": "Organization"}],
            "relationships": [{"source": "A", "type": "WORKS_AT"}],  # missing target
        }
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    result = extract_entities_and_relationships("text")

    assert result.entities == []
    assert result.relationships == []


def test_extract_retries_once_on_a_5xx_then_succeeds(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return _openrouter_response(503, body={"error": "unavailable"})
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = extract_entities_and_relationships("text")

    assert len(calls) == 2
    assert len(result.entities) == 2


def test_extract_retries_once_on_a_timeout_then_succeeds(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.TimeoutException("timed out")
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = extract_entities_and_relationships("text")

    assert len(calls) == 2
    assert len(result.entities) == 2


def test_extract_retries_once_on_malformed_json_then_succeeds(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return _openrouter_response(200, content="not valid json{{{")
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = extract_entities_and_relationships("text")

    assert len(calls) == 2
    assert len(result.entities) == 2


def test_extract_raises_extraction_error_after_retries_exhausted(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        return _openrouter_response(503, body={"error": "unavailable"})

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    with pytest.raises(ExtractionError):
        extract_entities_and_relationships("text")

    assert len(calls) == llm_client_module._MAX_ATTEMPTS


def test_extract_a_4xx_response_is_not_retried(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        return _openrouter_response(401, body={"error": "invalid api key"})

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    with pytest.raises(ExtractionError):
        extract_entities_and_relationships("text")

    assert len(calls) == 1
