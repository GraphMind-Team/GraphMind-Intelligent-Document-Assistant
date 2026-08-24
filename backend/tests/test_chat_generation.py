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
covered further down.

Story 3.5 adds two more sections, both at the bottom of this file:
`resolve_question` (intent classification/query rewrite, and its
never-raises fallback contract) and the `kind="grounded"/"prose"`
segment split (citation enforcement still applies to "grounded" only,
the `_MAX_PROSE_SEGMENTS` cap, and `generate_answer(mode="overview")`'s
own prompt/budget).
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
    QuestionPlan,
    bound_chat_history,
    generate_answer,
    resolve_question,
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
    monkeypatch.delenv("OPENROUTER_ROUTER_MODEL", raising=False)


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


def test_bound_chat_history_skips_an_oversized_newest_turn_but_keeps_older_ones(monkeypatch):
    """An individual turn that alone blows the whole budget must be
    skipped, not treated as a stop signal that discards the older turns
    behind it. Reachable in production, not exotic: `AskRequest.question`
    permits 2000 characters, so one maximal question already exceeds
    `HISTORY_MAX_CHARS` on its own -- with a `break`, asking it would zero
    the conversational-memory window outright for the following
    `HISTORY_MAX_TURNS` questions."""
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_TURNS", 3)
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_CHARS", 100)
    turns = [
        ChatHistoryTurn(question="older question", answer="older answer"),
        ChatHistoryTurn(question="middle question", answer="middle answer"),
        ChatHistoryTurn(question="q" * 500, answer="a" * 500),
    ]

    bounded = bound_chat_history(turns)

    assert [t.question for t in bounded] == ["older question", "middle question"]


def test_bound_chat_history_returns_empty_when_no_single_turn_fits(monkeypatch):
    """Skipping is per-turn, not a fallback that eventually gives up on
    the budget -- if nothing fits, nothing is returned."""
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_TURNS", 3)
    monkeypatch.setattr(llm_client_module, "HISTORY_MAX_CHARS", 10)
    turns = [ChatHistoryTurn(question="q" * 50, answer="a" * 50) for _ in range(3)]

    assert bound_chat_history(turns) == []


def test_bound_chat_history_empty_input_returns_empty_list():
    assert bound_chat_history([]) == []


def test_bound_chat_history_default_constants_are_three_turns_and_2000_chars():
    """Regression guard on the actual shipped values -- the tests above
    monkeypatch these to keep their own math simple, so nothing else
    asserts the real defaults the Boundaries specify ("last 3 prior
    turns, capped at 2000 total characters")."""
    assert llm_client_module.HISTORY_MAX_TURNS == 3
    assert llm_client_module.HISTORY_MAX_CHARS == 2000


# ---------------------------------------------------------------------------
# Story 3.5: resolve_question (intent classification / query rewrite).
# ---------------------------------------------------------------------------


def _router_content(intent="factual", search_query="rewritten query", reply=""):
    return json.dumps({"intent": intent, "search_query": search_query, "reply": reply})


def test_resolve_question_returns_the_models_intent_and_rewritten_query(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx,
        "post",
        lambda *a, **k: _openrouter_response(
            200, content=_router_content(intent="factual", search_query="What is Project Aurora's budget?")
        ),
    )

    plan = resolve_question("what about its budget?", [])

    assert plan == QuestionPlan(
        intent="factual", search_query="What is Project Aurora's budget?", reply=None
    )


def test_resolve_question_greeting_intent_carries_the_reply(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx,
        "post",
        lambda *a, **k: _openrouter_response(
            200, content=_router_content(intent="greeting", search_query="hello", reply="Hi there!")
        ),
    )

    plan = resolve_question("hello", [])

    assert plan.intent == "greeting"
    assert plan.reply == "Hi there!"


def test_resolve_question_greeting_with_blank_reply_falls_back_to_factual(monkeypatch):
    """A "greeting" intent with nothing usable to render must not reach
    `chat/service.py`'s greeting branch empty-handed -- the whole plan
    degrades, not just the field."""
    monkeypatch.setattr(
        llm_client_module.httpx,
        "post",
        lambda *a, **k: _openrouter_response(
            200, content=_router_content(intent="greeting", search_query="hello", reply="   ")
        ),
    )

    plan = resolve_question("hello", [])

    assert plan == QuestionPlan(intent="factual", search_query="hello", reply=None)


def test_resolve_question_out_of_vocabulary_intent_defaults_to_factual(monkeypatch, caplog):
    monkeypatch.setattr(
        llm_client_module.httpx,
        "post",
        lambda *a, **k: _openrouter_response(
            200, content=_router_content(intent="chitchat", search_query="rewritten")
        ),
    )

    with caplog.at_level("WARNING"):
        plan = resolve_question("some question", [])

    assert plan.intent == "factual"
    assert plan.search_query == "rewritten"
    assert "out-of-vocabulary intent" in caplog.text


def test_resolve_question_unhashable_intent_defaults_to_factual(monkeypatch, caplog):
    """Regression: `intent not in _ROUTER_ALLOWED_INTENTS` used to be
    checked before confirming `intent` was even hashable, so a model
    returning a list/object for `intent` (instead of a string) raised
    `TypeError` -- not a `_RouterCallError`, so it escaped
    `resolve_question`'s "never raises" contract and, since
    `chat/service.py` deliberately has no `try`/`except` around this
    call, would have 500'd `/chat/ask` instead of degrading to
    `factual`."""
    content = json.dumps({"intent": ["factual"], "search_query": "rewritten", "reply": ""})
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    with caplog.at_level("WARNING"):
        plan = resolve_question("some question", [])

    assert plan.intent == "factual"
    assert plan.search_query == "rewritten"
    assert "out-of-vocabulary intent" in caplog.text


def test_resolve_question_never_raises_on_a_null_content_body(monkeypatch):
    """Regression: `_parse_and_validate_plan` used to catch only
    `json.JSONDecodeError`, but a provider that answers with
    `"content": null` (some free-tier models do, putting their output in
    a sibling field instead) hands `json.loads` a `None`, which is a
    `TypeError`, not a decode error -- uncaught, it broke the
    never-raises contract the same way the two `TypeError`s above did."""
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=None)
    )

    plan = resolve_question("a question", [])

    assert plan == QuestionPlan(intent="factual", search_query="a question", reply=None)


def test_resolve_question_blank_search_query_falls_back_to_the_original_question(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx,
        "post",
        lambda *a, **k: _openrouter_response(200, content=_router_content(search_query="   ")),
    )

    plan = resolve_question("the original question", [])

    assert plan.search_query == "the original question"


def test_resolve_question_never_raises_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content="not json")
    )

    plan = resolve_question("a question", [])

    assert plan == QuestionPlan(intent="factual", search_query="a question", reply=None)


def test_resolve_question_never_raises_on_a_5xx_response(monkeypatch):
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(500, content="boom")
    )

    plan = resolve_question("a question", [])

    assert plan == QuestionPlan(intent="factual", search_query="a question", reply=None)


def test_resolve_question_never_raises_on_a_timeout(monkeypatch):
    def _raise_timeout(*a, **k):
        raise httpx.TimeoutException("router timed out", request=_REQUEST)

    monkeypatch.setattr(llm_client_module.httpx, "post", _raise_timeout)

    plan = resolve_question("a question", [])

    assert plan == QuestionPlan(intent="factual", search_query="a question", reply=None)


def test_resolve_question_never_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    plan = resolve_question("a question", [])

    assert plan == QuestionPlan(intent="factual", search_query="a question", reply=None)


def test_resolve_question_is_never_retried(monkeypatch):
    """Unlike `generate_answer`'s `_CHAT_MAX_ATTEMPTS`, a router failure
    degrades to the fallback on the first failure -- a second attempt
    would only add latency in front of the real answer for a call whose
    failure mode already has a safe, cheap fallback."""
    calls = []

    def _raise_timeout(*a, **k):
        calls.append(1)
        raise httpx.TimeoutException("router timed out", request=_REQUEST)

    monkeypatch.setattr(llm_client_module.httpx, "post", _raise_timeout)

    resolve_question("a question", [])

    assert len(calls) == 1


def test_resolve_question_folds_history_into_the_request(monkeypatch):
    captured = {}

    def _fake_post(url, *, headers, json, timeout):
        captured["system_prompt"] = json["messages"][0]["content"]
        return _openrouter_response(200, content=_router_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    resolve_question(
        "what about its budget?",
        [ChatHistoryTurn(question="Who is the vendor?", answer="TechCorp is the vendor.")],
    )

    assert "Who is the vendor?" in captured["system_prompt"]


def test_resolve_question_uses_router_model_override_when_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_ROUTER_MODEL", "test/router-model:free")
    captured = {}

    def _fake_post(url, *, headers, json, timeout):
        captured["model"] = json["model"]
        return _openrouter_response(200, content=_router_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    resolve_question("a question", [])

    assert captured["model"] == "test/router-model:free"


def test_resolve_question_falls_back_to_chat_model_when_router_model_unset(monkeypatch):
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "test/chat-model:free")
    captured = {}

    def _fake_post(url, *, headers, json, timeout):
        captured["model"] = json["model"]
        return _openrouter_response(200, content=_router_content())

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    resolve_question("a question", [])

    assert captured["model"] == "test/chat-model:free"


# ---------------------------------------------------------------------------
# Story 3.5: "grounded"/"prose" segment kinds.
# ---------------------------------------------------------------------------


def test_generate_answer_prose_segment_survives_with_no_citations(monkeypatch):
    content = json.dumps(
        {
            "segments": [
                {"text": "Sure, here's what I found:", "kind": "prose", "passage_numbers": []},
                {
                    "text": "TechCorp's refund window is 30 days.",
                    "kind": "grounded",
                    "passage_numbers": [1],
                },
            ]
        }
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    result = generate_answer("What is the refund window?", [_passage()])

    assert [s.kind for s in result.segments] == ["prose", "grounded"]
    assert result.segments[0].passage_numbers == []
    assert result.segments[1].passage_numbers == [1]


def test_generate_answer_grounded_segment_without_citation_is_still_dropped(monkeypatch):
    """`kind="grounded"` (explicit, not just the default) is held to the
    same citation requirement as pre-3.5 -- "prose" is the only exemption,
    never a value that happens to have no passage_numbers."""
    content = json.dumps(
        {"segments": [{"text": "An uncited claim.", "kind": "grounded", "passage_numbers": []}]}
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    result = generate_answer("A question?", [_passage()])

    assert result.segments == []


def test_generate_answer_missing_kind_defaults_to_grounded(monkeypatch):
    """A response with no `kind` key at all (an older prompt shape, or a
    provider that ignores the field) must still be held to the citation
    requirement -- never silently treated as unchecked prose."""
    content = json.dumps({"segments": [{"text": "An uncited claim.", "passage_numbers": []}]})
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    result = generate_answer("A question?", [_passage()])

    assert result.segments == []


def test_generate_answer_out_of_vocabulary_kind_defaults_to_grounded(monkeypatch, caplog):
    content = json.dumps(
        {
            "segments": [
                {"text": "Some text.", "kind": "sarcastic", "passage_numbers": [1]},
            ]
        }
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    with caplog.at_level("WARNING"):
        result = generate_answer("A question?", [_passage()])

    assert result.segments[0].kind == "grounded"
    assert "out-of-vocabulary kind" in caplog.text


def test_generate_answer_unhashable_kind_defaults_to_grounded_instead_of_raising(monkeypatch, caplog):
    """Regression: `raw_kind in _VALID_SEGMENT_KINDS` used to be checked
    before confirming `raw_kind` was even hashable, so a model returning
    a list/object for `kind` (instead of a string) raised `TypeError` --
    not a `_RetryableChatError`, so it escaped `generate_answer`'s retry
    loop entirely and surfaced as an unhandled 500 rather than the
    documented "default to grounded" behaviour every other malformed
    `kind` value already gets."""
    content = json.dumps(
        {
            "segments": [
                {"text": "Some text.", "kind": ["grounded"], "passage_numbers": [1]},
            ]
        }
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    with caplog.at_level("WARNING"):
        result = generate_answer("A question?", [_passage()])

    assert result.segments[0].kind == "grounded"
    assert "out-of-vocabulary kind" in caplog.text


def test_generate_answer_caps_prose_segments_at_the_configured_maximum(monkeypatch):
    content = json.dumps(
        {
            "segments": [
                {"text": "Prose one.", "kind": "prose", "passage_numbers": []},
                {"text": "Prose two.", "kind": "prose", "passage_numbers": []},
                {"text": "Prose three.", "kind": "prose", "passage_numbers": []},
                {"text": "A grounded claim.", "kind": "grounded", "passage_numbers": [1]},
            ]
        }
    )
    monkeypatch.setattr(
        llm_client_module.httpx, "post", lambda *a, **k: _openrouter_response(200, content=content)
    )

    result = generate_answer("A question?", [_passage()])

    prose_segments = [s for s in result.segments if s.kind == "prose"]
    assert len(prose_segments) == llm_client_module._MAX_PROSE_SEGMENTS
    assert [s.text for s in prose_segments] == ["Prose one.", "Prose two."]
    assert any(s.kind == "grounded" for s in result.segments)


# ---------------------------------------------------------------------------
# Story 3.5: generate_answer(mode="overview").
# ---------------------------------------------------------------------------


def test_generate_answer_overview_mode_includes_document_structure_in_the_prompt(monkeypatch):
    captured = {}

    def _fake_post(url, *, headers, json, timeout):
        captured["system_prompt"] = json["messages"][0]["content"]
        captured["timeout"] = timeout
        return _openrouter_response(200, content='{"segments": []}')

    monkeypatch.setattr(llm_client_module.httpx, "post", _fake_post)

    generate_answer(
        "What is this document about?",
        [_passage()],
        mode="overview",
        document_structure="report.pdf:\n  - Introduction: 3 passages",
    )

    assert "report.pdf" in captured["system_prompt"]
    assert "Introduction: 3 passages" in captured["system_prompt"]
    assert captured["timeout"] == llm_client_module._OVERVIEW_TIMEOUT_SECONDS


def test_select_overview_passages_within_budget_returns_everything_when_it_fits():
    passages = [_passage(chunk_id=f"chunk-{i}") for i in range(3)]

    selected = llm_client_module._select_overview_passages_within_budget(passages)

    assert selected == passages


def test_select_overview_passages_within_budget_samples_across_the_whole_list_when_over_budget(
    monkeypatch,
):
    """Unlike `_select_passages_within_budget`'s tail-drop (correct for a
    nearest-first relevance-ranked list), an overview's passage list has
    no relevance ordering -- dropping the tail would silently summarize
    only the document's first pages. An even stride must keep passages
    from across the whole list, not just a contiguous prefix."""
    monkeypatch.setattr(llm_client_module, "_OVERVIEW_MAX_PROMPT_CHARS", 200)
    passages = [_passage(chunk_id=f"chunk-{i}", text="x" * 50) for i in range(10)]

    selected = llm_client_module._select_overview_passages_within_budget(passages)

    assert 1 <= len(selected) < len(passages)
    # Not merely a prefix -- the surviving indices must skip ahead rather
    # than being a contiguous run starting at 0, which is what a stride
    # sample looks like and a tail-drop-style selection never would.
    indices = sorted(int(p.chunk_id.split("-")[1]) for p in selected)
    assert indices != list(range(len(indices)))
