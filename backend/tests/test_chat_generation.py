"""`shared/llm_client.generate_answer` tests (Story 3.1): the structured-
citation JSON contract, out-of-range/uncited-segment dropping, the empty-
result-is-not-an-error outcome, the chat-tuned retry budget (timeout/5xx/
429/malformed JSON, honoring Retry-After), the non-retryable-4xx path, the
prompt-size budget dropping whole trailing passages, and the
OPENROUTER_CHAT_MODEL override. Mirrors `test_entity_extraction.py`'s
approach: mocks `httpx.post`, builds real `httpx.Response` objects so
`raise_for_status` behaves correctly, and monkeypatches `time.sleep`.

Story 3.4/FR-17 adds `bound_chat_history` (the HISTORY_MAX_TURNS/
HISTORY_MAX_CHARS budgeting) and `generate_answer`'s new `history` param,
covered at the bottom of this file.
"""

import json

import httpx
import pytest

from app.shared import llm_client as llm_client_module
from app.shared.data_access.shapes import WeaviateSearchResult
from app.shared.llm_client import (
    AnswerResult,
    ChatCompletionError,
    ChatHistoryTurn,
    bound_chat_history,
    generate_answer,
)

_REQUEST = httpx.Request("POST", llm_client_module.OPENROUTER_URL)


def _openrouter_response(status_code, *, content=None, body=None, headers=None):
    if body is None:
        body = {"choices": [{"message": {"content": content}}]}
    return httpx.Response(status_code, json=body, request=_REQUEST, headers=headers)


@pytest.fixture(autouse=True)
def _openrouter_api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_CHAT_MODEL", raising=False)


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    slept = []
    monkeypatch.setattr(llm_client_module.time, "sleep", slept.append)
    return slept


def _passage(chunk_id="chunk-0", document_id="doc-1", chapter="Chapter One", text="passage text"):
    return WeaviateSearchResult(
        chunk_id=chunk_id,
        document_id=document_id,
        chapter=chapter,
        chunk_index=0,
        text=text,
        distance=0.1,
    )


def _valid_content(passage_numbers=(1,)):
    return json.dumps(
        {"segments": [{"text": "TechCorp's refund window is 30 days.", "passage_numbers": list(passage_numbers)}]}
    )


def test_generate_answer_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        generate_answer("What is the refund window?", [_passage()])


def test_generate_answer_returns_segments_with_resolved_citations_on_success(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=_valid_content())
    )

    passage = _passage()
    result = generate_answer("What is the refund window?", [passage])

    assert isinstance(result, AnswerResult)
    assert len(result.segments) == 1
    assert result.segments[0].text == "TechCorp's refund window is 30 days."
    assert result.segments[0].passage_numbers == [1]
    # The exact list the prompt was built from -- chat/service.py resolves
    # citations against this, not the caller's original `passages`.
    assert result.included_passages == [passage]


def test_generate_answer_empty_segments_is_a_valid_outcome_not_an_error(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx,
        "post",
        lambda *a, **k: _openrouter_response(200, content=json.dumps({"segments": []})),
    )

    result = generate_answer("An unanswerable question", [_passage()])

    assert result.segments == []


def test_generate_answer_drops_out_of_range_passage_number_but_keeps_valid_ones(monkeypatch, caplog):
    content = json.dumps(
        {"segments": [{"text": "A claim.", "passage_numbers": [1, 99]}]}
    )
    monkeypatch.setattr(llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content))

    with caplog.at_level("WARNING"):
        result = generate_answer("q", [_passage()])

    assert len(result.segments) == 1
    assert result.segments[0].passage_numbers == [1]
    assert "out-of-range" in caplog.text


def test_generate_answer_logs_a_stray_boolean_as_invalid_not_silently(monkeypatch, caplog):
    """`True == 1` in Python -- a naive `n not in valid_numbers` membership
    check would silently drop a stray boolean into neither the valid nor
    the logged-invalid list. It's excluded from the response either way
    (booleans are never valid passage numbers), but it must still show up
    in the warning log rather than vanishing untraced."""
    content = json.dumps({"segments": [{"text": "A claim.", "passage_numbers": [1, True]}]})
    monkeypatch.setattr(llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content))

    with caplog.at_level("WARNING"):
        result = generate_answer("q", [_passage()])

    assert result.segments[0].passage_numbers == [1]
    assert "out-of-range" in caplog.text
    assert "True" in caplog.text


def test_select_passages_within_budget_logs_when_it_truncates(monkeypatch, caplog):
    monkeypatch.setattr(llm_client_module, "_MAX_PROMPT_CHARS", 200)
    small_passage = _passage(chunk_id="chunk-0", text="short")
    huge_passage = _passage(chunk_id="chunk-1", text="x" * 500)

    # WARNING, not DEBUG: nothing in this project configures a root log
    # level, so only WARNING-and-above is guaranteed visible without extra
    # setup -- this test asserts the level that's actually reachable in
    # production, not merely that some level was used.
    with caplog.at_level("WARNING"):
        selected = llm_client_module._select_passages_within_budget([small_passage, huge_passage])

    assert len(selected) == 1
    assert "included 1/2 passages" in caplog.text
    assert caplog.records[0].levelname == "WARNING"


def test_select_passages_within_budget_logs_nothing_when_everything_fits(caplog):
    with caplog.at_level("WARNING"):
        llm_client_module._select_passages_within_budget([_passage()])

    assert caplog.text == ""


def test_select_passages_within_budget_always_includes_at_least_the_first_passage(monkeypatch):
    """A single passage too large to fit inside _MAX_PROMPT_CHARS on its own
    (e.g. a whitespace-stripped table or base64 blob, where the chunker's
    250-word split produces "words" hundreds of characters long) must still
    be included rather than leaving `selected` empty -- an empty passage
    block would still spend a real LLM call that can only ever come back
    with passage_count=0, an unanswerable question by construction every
    time, for a user with no way to know why."""
    monkeypatch.setattr(llm_client_module, "_MAX_PROMPT_CHARS", 200)
    oversized_passage = _passage(chunk_id="chunk-0", text="x" * 500)

    selected = llm_client_module._select_passages_within_budget([oversized_passage])

    assert selected == [oversized_passage]


def test_generate_answer_still_calls_the_model_when_the_only_passage_is_oversized(monkeypatch):
    """End-to-end: `generate_answer` must not skip calling the model (or
    build a prompt with zero passages) just because the sole retrieved
    passage overflows the budget on its own."""
    monkeypatch.setattr(llm_client_module, "_MAX_PROMPT_CHARS", 200)
    oversized_passage = _passage(chunk_id="chunk-0", text="x" * 500)

    captured = {}

    def _fake_post(*args, **kwargs):
        captured["system_prompt"] = kwargs["json"]["messages"][0]["content"]
        return _openrouter_response(200, content=_valid_content(passage_numbers=[1]))

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = generate_answer("q", [oversized_passage])

    assert "Passage 1" in captured["system_prompt"]
    assert result.included_passages == [oversized_passage]
    assert len(result.segments) == 1


def test_generate_answer_drops_segment_with_no_valid_citations(monkeypatch):
    content = json.dumps(
        {
            "segments": [
                {"text": "Uncited claim.", "passage_numbers": [99]},
                {"text": "Cited claim.", "passage_numbers": [1]},
            ]
        }
    )
    monkeypatch.setattr(llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content))

    result = generate_answer("q", [_passage()])

    assert [s.text for s in result.segments] == ["Cited claim."]


def test_generate_answer_drops_segment_with_blank_text(monkeypatch):
    content = json.dumps({"segments": [{"text": "  ", "passage_numbers": [1]}]})
    monkeypatch.setattr(llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content))

    result = generate_answer("q", [_passage()])

    assert result.segments == []


def test_generate_answer_retries_once_on_a_5xx_then_succeeds(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return _openrouter_response(503, body={"error": "unavailable"})
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = generate_answer("q", [_passage()])

    assert len(calls) == 2
    assert len(result.segments) == 1


def test_generate_answer_retries_once_on_a_timeout_then_succeeds(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.TimeoutException("timed out")
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = generate_answer("q", [_passage()])

    assert len(calls) == 2
    assert len(result.segments) == 1


def test_generate_answer_retries_once_on_malformed_json_then_succeeds(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return _openrouter_response(200, content="not valid json{{{")
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = generate_answer("q", [_passage()])

    assert len(calls) == 2
    assert len(result.segments) == 1


def test_generate_answer_raises_chat_completion_error_after_retries_exhausted(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        return _openrouter_response(503, body={"error": "unavailable"})

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    with pytest.raises(ChatCompletionError):
        generate_answer("q", [_passage()])

    assert len(calls) == llm_client_module._CHAT_MAX_ATTEMPTS


def test_generate_answer_a_4xx_response_is_not_retried(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        return _openrouter_response(401, body={"error": "invalid api key"})

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    with pytest.raises(ChatCompletionError):
        generate_answer("q", [_passage()])

    assert len(calls) == 1


def test_generate_answer_retries_a_429_rate_limit_and_can_still_succeed(monkeypatch):
    calls = []

    def _fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return _openrouter_response(429, body={"error": {"message": "rate-limited", "code": 429}})
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = generate_answer("q", [_passage()])

    assert len(calls) == 2
    assert len(result.segments) == 1


def test_generate_answer_honours_a_429_retry_after_header(monkeypatch, _no_real_sleeping):
    def _fake_post(*args, **kwargs):
        return _openrouter_response(429, body={"error": "slow down"}, headers={"Retry-After": "12"})

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    with pytest.raises(ChatCompletionError):
        generate_answer("q", [_passage()])

    assert _no_real_sleeping == [12.0]


def test_generate_answer_uses_default_model_when_chat_model_env_unset(monkeypatch):
    captured = {}

    def _fake_post(*args, **kwargs):
        captured["model"] = kwargs["json"]["model"]
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    generate_answer("q", [_passage()])

    assert captured["model"] == llm_client_module.DEFAULT_MODEL


def test_generate_answer_uses_openrouter_chat_model_override_when_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "some/faster-model:free")
    captured = {}

    def _fake_post(*args, **kwargs):
        captured["model"] = kwargs["json"]["model"]
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    generate_answer("q", [_passage()])

    assert captured["model"] == "some/faster-model:free"


def test_generate_answer_prompt_budget_drops_whole_trailing_passages(monkeypatch):
    """A passage too large to fit is dropped wholesale (not truncated
    mid-passage), and the numbering the model is shown -- and validated
    against on the way back -- only covers the passages actually
    included."""
    monkeypatch.setattr(llm_client_module, "_MAX_PROMPT_CHARS", 200)
    small_passage = _passage(chunk_id="chunk-0", text="short")
    huge_passage = _passage(chunk_id="chunk-1", text="x" * 500)

    captured = {}

    def _fake_post(*args, **kwargs):
        captured["system_prompt"] = kwargs["json"]["messages"][0]["content"]
        # The model is asked to cite passage 2 -- which doesn't exist in the
        # trimmed prompt, since only passage 1 fit the budget.
        return _openrouter_response(200, content=_valid_content(passage_numbers=[2]))

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    result = generate_answer("q", [small_passage, huge_passage])

    assert "Passage 2" not in captured["system_prompt"]
    # passage_numbers=[2] is out of range against only 1 included passage,
    # so the segment citing it is dropped entirely.
    assert result.segments == []
    # The trimmed list, not the original two-passage input -- this is what
    # chat/service.py would resolve citations against.
    assert result.included_passages == [small_passage]


# ---------------------------------------------------------------------------
# Story 3.4/FR-17: history threading and `bound_chat_history` budgeting.
# ---------------------------------------------------------------------------


def test_generate_answer_with_no_history_produces_the_exact_pre_3_4_prompt(monkeypatch):
    """Boundaries: "a fresh conversation with zero prior turns behaves
    identically to today's stateless flow" -- asserted here at the
    strongest level, byte-identical prompt text, not just equivalent
    behavior."""
    captured = {}

    def _fake_post(*args, **kwargs):
        captured["system_prompt"] = kwargs["json"]["messages"][0]["content"]
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    generate_answer("q", [_passage()])
    prompt_without_history = captured["system_prompt"]

    generate_answer("q", [_passage()], history=[])
    prompt_with_empty_history_list = captured["system_prompt"]

    generate_answer("q", [_passage()], history=None)
    prompt_with_explicit_none = captured["system_prompt"]

    assert prompt_without_history == prompt_with_empty_history_list == prompt_with_explicit_none


def test_generate_answer_folds_history_into_the_system_prompt_as_q_and_a(monkeypatch):
    captured = {}

    def _fake_post(*args, **kwargs):
        captured["system_prompt"] = kwargs["json"]["messages"][0]["content"]
        return _openrouter_response(200, content=_valid_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    history = [ChatHistoryTurn(question="Who is the vendor?", answer="TechCorp is the vendor.")]
    generate_answer("What about its refund window?", [_passage()], history=history)

    assert "Q: Who is the vendor?" in captured["system_prompt"]
    assert "A: TechCorp is the vendor." in captured["system_prompt"]
    # History precedes the passage block (Design Notes: "appended before
    # the passage block").
    assert captured["system_prompt"].index("Who is the vendor?") < captured["system_prompt"].index(
        "Passage 1"
    )


def test_bound_chat_history_caps_at_history_max_turns(monkeypatch):
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_TURNS", 2)
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_CHARS", 10_000)
    turns = [ChatHistoryTurn(question=f"q{i}", answer=f"a{i}") for i in range(5)]

    bounded = bound_chat_history(turns)

    # The newest 2 turns survive, oldest-first order preserved.
    assert [t.question for t in bounded] == ["q3", "q4"]


def test_bound_chat_history_drops_oldest_turns_first_when_over_char_budget(monkeypatch):
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_TURNS", 10)
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_CHARS", 40)
    turns = [
        ChatHistoryTurn(question="oldest question", answer="oldest answer"),
        ChatHistoryTurn(question="newest question", answer="newest answer"),
    ]

    bounded = bound_chat_history(turns)

    # Only the newest turn fits inside the 40-char budget -- the oldest is
    # dropped, not truncated.
    assert [t.question for t in bounded] == ["newest question"]


def test_bound_chat_history_never_exceeds_the_char_budget(monkeypatch):
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_TURNS", 3)
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_CHARS", 2000)
    turns = [ChatHistoryTurn(question="q" * 100, answer="a" * 900) for _ in range(3)]

    bounded = bound_chat_history(turns)

    total_chars = sum(len(f"Q: {t.question}\nA: {t.answer}\n") for t in bounded)
    assert total_chars <= 2000


def test_bound_chat_history_empty_input_returns_empty_list():
    assert bound_chat_history([]) == []


def test_bound_chat_history_default_constants_are_three_turns_and_2000_chars():
    """Regression guard on the actual shipped values -- the tests above
    monkeypatch these to keep their own math simple, so nothing else
    asserts the real defaults the Boundaries specify ("last 3 prior
    turns, capped at 2000 total characters")."""
    assert llm_client_module.HISTORY_MAX_TURNS == 3
    assert llm_client_module.HISTORY_MAX_CHARS == 2000
