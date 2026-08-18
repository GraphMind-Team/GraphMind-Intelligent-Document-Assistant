"""`scripts/eval_harness.py` scoring/classification/aggregation tests
(Story 6.1).

Unit-tests the pure scoring/decision/aggregation functions against fake
`AskResponse` objects, fake upload outcomes, and fake `QuestionRunResult`
lists -- one case per row of the spec's I/O & Edge-Case Matrix, plus the
review-flagged gaps (load-time question-set validation, per-question
exception isolation, the aggregation math behind SM-1/SM-2/SM-C1, fresh-
ingestion timeout, env-var validation) -- never against a live
DB/Weaviate/Neo4j/OpenRouter. `_run_question`/`_run_ingest_with_timeout`
are exercised with injected fakes for the same reason (mirrors
`ingest_document`'s own `session_factory` injection pattern elsewhere in
this codebase).
"""

import json
import pathlib
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.chat.schemas import AnswerSegmentResponse, AskResponse
from app.shared.data_access.weaviate_client import TOP_K_PASSAGES
from app.shared.llm_client import RELEVANCE_THRESHOLD
from app.shared.models import Document
from scripts.eval_harness import (
    FIXTURES_DIR,
    QUESTIONS_PATH,
    REQUIRED_ENV_VARS,
    EvalHarnessError,
    QuestionRunResult,
    ScopeError,
    _decide_fixture_action,
    _load_questions,
    _percent,
    _poll_until_terminal,
    _print_report,
    _run_ingest_with_timeout,
    _run_question,
    _safe_close,
    _text_matches,
    _validate_env,
    classify_answerable,
    classify_unanswerable,
)


def _answer(text: str | None = None, *, empty_reason=None) -> AskResponse:
    if empty_reason is not None:
        return AskResponse(segments=[], empty_reason=empty_reason)
    return AskResponse(segments=[AnswerSegmentResponse(text=text, citations=[])])


def _question(*, category="factual", must_contain=None, match="all", qid="q1"):
    return {
        "id": qid,
        "category": category,
        "must_contain": must_contain if must_contain is not None else [],
        "match": match,
    }


def _document(status="Extracting", document_id=None):
    return Document(
        id=document_id or uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="f.md",
        file_type="markdown",
        file_size_bytes=1,
        status=status,
        content=b"x",
        content_hash="h",
    )


def _result(question_id, category, status, is_refusal=False, detail=""):
    return QuestionRunResult(
        question_id=question_id, category=category, status=status, is_refusal=is_refusal, detail=detail
    )


# ---------------------------------------------------------------------------
# _text_matches -- the deterministic substring scoring underlying row 1
# ---------------------------------------------------------------------------


def test_text_matches_all_requires_every_needle():
    assert _text_matches("The budget is $184,000 total.", ["$184,000"], "all") is True
    assert _text_matches("The budget is $184,000 total.", ["$184,000", "missing"], "all") is False


def test_text_matches_any_requires_only_one_needle():
    assert _text_matches("Ships 2026-09-15.", ["2026-09-15", "September 15, 2026"], "any") is True
    assert _text_matches("Ships later this year.", ["2026-09-15", "September 15, 2026"], "any") is False


def test_text_matches_is_case_insensitive():
    assert _text_matches("ELENA RUSEV leads it.", ["elena rusev"], "all") is True


def test_text_matches_rejects_unknown_mode_with_eval_harness_error():
    # Not a bare ValueError -- everything this module raises for a known
    # failure mode is an EvalHarnessError, so main()'s single except
    # clause catches it cleanly (review finding #1).
    with pytest.raises(EvalHarnessError):
        _text_matches("text", ["x"], "bogus")


# ---------------------------------------------------------------------------
# Row 1: factual/synthesis question scored via must_contain
# ---------------------------------------------------------------------------


def test_classify_answerable_correct_when_answer_matches():
    question = _question(must_contain=["$184,000"], match="all")
    response = _answer("Project Aurora's budget is $184,000.")

    verdict, is_refusal = classify_answerable(question, response)

    assert verdict == "correct"
    assert is_refusal is False


def test_classify_answerable_incorrect_when_answer_does_not_match():
    question = _question(must_contain=["$184,000"], match="all")
    response = _answer("Project Aurora's budget is not stated here.")

    verdict, is_refusal = classify_answerable(question, response)

    assert verdict == "incorrect"
    assert is_refusal is False


def test_classify_answerable_no_answer_is_incorrect_but_not_a_refusal():
    # Distinct from a refusal per the spec's Boundaries: passages were
    # relevant enough not to refuse, but nothing citable came out.
    question = _question(must_contain=["$184,000"], match="all")
    response = _answer(empty_reason="no_answer")

    verdict, is_refusal = classify_answerable(question, response)

    assert verdict == "incorrect"
    assert is_refusal is False


# ---------------------------------------------------------------------------
# Row 2: refusal on an answerable question -- incorrect *and* feeds SM-C1
# ---------------------------------------------------------------------------


def test_classify_answerable_refusal_is_incorrect_and_feeds_sm_c1():
    question = _question(must_contain=["$184,000"], match="all")
    response = _answer(empty_reason="refusal")

    verdict, is_refusal = classify_answerable(question, response)

    assert verdict == "incorrect"
    assert is_refusal is True


# ---------------------------------------------------------------------------
# Row 3: unanswerable question -- refusal correct, no_answer benign,
# empty_scope aborts, an actual answer is an SM-2 violation
# ---------------------------------------------------------------------------


def test_classify_unanswerable_refusal_is_the_desired_outcome():
    question = _question(category="unanswerable")
    response = _answer(empty_reason="refusal")

    assert classify_unanswerable(question, response) == "refusal"


def test_classify_unanswerable_no_answer_is_logged_separately_not_a_violation():
    question = _question(category="unanswerable")
    response = _answer(empty_reason="no_answer")

    assert classify_unanswerable(question, response) == "no_answer"


def test_classify_unanswerable_an_actual_answer_is_a_violation():
    question = _question(category="unanswerable")
    response = _answer("Here is a confident, unsupported answer.")

    assert classify_unanswerable(question, response) == "violation"


@pytest.mark.parametrize("reason", ["no_documents", "empty_scope"])
def test_classify_answerable_scope_bug_aborts_rather_than_scores(reason):
    question = _question(must_contain=["x"], match="all")
    response = _answer(empty_reason=reason)

    with pytest.raises(ScopeError):
        classify_answerable(question, response)


@pytest.mark.parametrize("reason", ["no_documents", "empty_scope"])
def test_classify_unanswerable_scope_bug_aborts_rather_than_scores(reason):
    question = _question(category="unanswerable")
    response = _answer(empty_reason=reason)

    with pytest.raises(ScopeError):
        classify_unanswerable(question, response)


# ---------------------------------------------------------------------------
# Row 4: ask_question failure mid-run -- logged as an error, run
# continues, excluded from every metric; never scored as a refusal.
# Broadened (review finding #2) to any exception, not just a 503.
# ---------------------------------------------------------------------------


def test_run_question_treats_a_503_as_a_run_error_not_a_refusal():
    document_id = uuid.uuid4()
    question = {
        "id": "q99",
        "category": "factual",
        "question": "does not matter",
        "document_filenames": ["fixture.md"],
        "must_contain": ["x"],
        "match": "all",
    }
    document_ids_by_filename = {"fixture.md": document_id}

    def _raising_ask_fn(db, user, question_text, document_ids):
        raise HTTPException(status_code=503, detail="Answer generation is temporarily unavailable.")

    result = _run_question(
        db=None, user=None, question=question, document_ids_by_filename=document_ids_by_filename,
        ask_fn=_raising_ask_fn,
    )

    assert result.status == "error"
    assert result.is_refusal is False
    assert "503" in result.detail


def test_run_question_treats_a_non_503_http_exception_as_a_run_error_too():
    document_id = uuid.uuid4()
    question = {
        "id": "q100",
        "category": "factual",
        "question": "does not matter",
        "document_filenames": ["fixture.md"],
        "must_contain": [],
        "match": "all",
    }
    document_ids_by_filename = {"fixture.md": document_id}

    def _raising_ask_fn(db, user, question_text, document_ids):
        raise HTTPException(status_code=404, detail="not found")

    result = _run_question(
        db=None, user=None, question=question, document_ids_by_filename=document_ids_by_filename,
        ask_fn=_raising_ask_fn,
    )

    assert result.status == "error"
    assert "404" in result.detail


def test_run_question_treats_any_other_exception_as_a_run_error_and_does_not_raise():
    # A transient Weaviate/Neo4j failure, or anything else ask_question's
    # call chain might raise -- must not abort the run and lose every
    # prior question's already-completed results.
    document_id = uuid.uuid4()
    question = {
        "id": "q101",
        "category": "factual",
        "question": "does not matter",
        "document_filenames": ["fixture.md"],
        "must_contain": [],
        "match": "all",
    }
    document_ids_by_filename = {"fixture.md": document_id}

    def _raising_ask_fn(db, user, question_text, document_ids):
        raise ConnectionError("Weaviate unreachable")

    result = _run_question(
        db=None, user=None, question=question, document_ids_by_filename=document_ids_by_filename,
        ask_fn=_raising_ask_fn,
    )

    assert result.status == "error"
    assert result.is_refusal is False
    assert "Weaviate unreachable" in result.detail


# ---------------------------------------------------------------------------
# _safe_close -- a dropped Neon idle connection at close-time must not kill
# the whole run (bug found running eval_harness.py live: an unguarded
# db.close() propagated an OperationalError out of the per-question loop's
# finally block, aborting every remaining question and the final report)
# ---------------------------------------------------------------------------


def test_safe_close_swallows_a_close_time_failure():
    class _DyingSession:
        def close(self):
            raise RuntimeError("SSL connection has been closed unexpectedly")

    _safe_close(_DyingSession())  # must not raise


def test_safe_close_still_closes_a_healthy_session():
    closed = []

    class _HealthySession:
        def close(self):
            closed.append(True)

    _safe_close(_HealthySession())

    assert closed == [True]


def test_run_question_scores_a_correct_answerable_response_end_to_end():
    document_id = uuid.uuid4()
    question = {
        "id": "q1",
        "category": "factual",
        "question": "What is the budget?",
        "document_filenames": ["fixture.md"],
        "must_contain": ["$184,000"],
        "match": "all",
    }
    document_ids_by_filename = {"fixture.md": document_id}

    def _fake_ask(db, user, question_text, document_ids):
        assert document_ids == [document_id]
        return AskResponse(segments=[AnswerSegmentResponse(text="$184,000.", citations=[])])

    result = _run_question(
        db=None, user=None, question=question, document_ids_by_filename=document_ids_by_filename,
        ask_fn=_fake_ask,
    )

    assert result.status == "correct"
    assert result.category == "factual"
    assert result.is_refusal is False


def test_run_question_scopes_to_the_whole_fixture_corpus_not_just_the_supporting_docs():
    # Scoping a question to the documents holding its own answer hands
    # retrieval the answer and measures only generation; the whole corpus
    # makes retrieval discriminate, as a real library would (review
    # finding). `document_filenames` stays documentation-only.
    supporting_id, other_id = uuid.uuid4(), uuid.uuid4()
    question = {
        "id": "q1",
        "category": "factual",
        "question": "What is the budget?",
        "document_filenames": ["supporting.md"],
        "must_contain": ["$184,000"],
        "match": "all",
    }
    document_ids_by_filename = {"supporting.md": supporting_id, "other.md": other_id}
    seen: list = []

    def _fake_ask(db, user, question_text, document_ids):
        seen.append(document_ids)
        return AskResponse(segments=[AnswerSegmentResponse(text="$184,000.", citations=[])])

    _run_question(
        db=None, user=None, question=question, document_ids_by_filename=document_ids_by_filename,
        ask_fn=_fake_ask,
    )

    assert sorted(seen[0], key=str) == sorted([supporting_id, other_id], key=str)


def test_run_question_aborts_with_a_clear_error_when_a_fixture_reference_is_unknown():
    # A KeyError here means eval_questions.json references a fixture that
    # was never ingested -- a data-integrity bug, not a live-service
    # flake, so this must hard-abort rather than being swallowed as a
    # per-question run error (review finding #1).
    question = {
        "id": "q102",
        "category": "factual",
        "question": "does not matter",
        "document_filenames": ["does-not-exist.md"],
        "must_contain": [],
        "match": "all",
    }

    with pytest.raises(EvalHarnessError, match="does-not-exist.md"):
        _run_question(db=None, user=None, question=question, document_ids_by_filename={})


# ---------------------------------------------------------------------------
# Row 5: re-running the harness -- re-ingest only if not Ready/not stuck,
# poll with timeout, never silently re-drive a stuck fixture. Fresh
# ingestion now shares the same timeout bound (review finding #6).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome,status,expected",
    [
        ("created", "Uploaded", "ingest"),
        ("reingested", "Uploaded", "ingest"),
        ("duplicate", "Ready", "reuse"),
        ("duplicate", "Uploaded", "poll_or_abort"),
        ("duplicate", "Extracting", "poll_or_abort"),
        ("duplicate", "Graphing", "poll_or_abort"),
    ],
)
def test_decide_fixture_action(outcome, status, expected):
    assert _decide_fixture_action(outcome, status) == expected


def test_decide_fixture_action_rejects_an_unknown_outcome_with_eval_harness_error():
    with pytest.raises(EvalHarnessError):
        _decide_fixture_action("bogus", "Ready")


def test_poll_until_terminal_returns_once_the_row_reaches_ready():
    document = _document(status="Extracting")
    statuses = iter(["Extracting", "Ready"])

    class _FakeDB:
        def expire_all(self):
            pass

        def get(self, model, document_id):
            document.status = next(statuses)
            return document

    sleeps = []
    result = _poll_until_terminal(
        _FakeDB(), document.id, timeout=100, interval=1, sleep=sleeps.append, now=lambda: 0,
    )

    assert result.status == "Ready"
    assert sleeps == [1]


def test_poll_until_terminal_aborts_after_timeout_rather_than_polling_forever():
    document = _document(status="Extracting")

    class _FakeDB:
        def expire_all(self):
            pass

        def get(self, model, document_id):
            return document  # never advances -- genuinely stuck

    clock = iter([0, 1, 2, 100])  # last value clears the 10s deadline
    with pytest.raises(EvalHarnessError, match="Timed out"):
        _poll_until_terminal(
            _FakeDB(), document.id, timeout=10, interval=1,
            sleep=lambda _: None, now=lambda: next(clock),
        )


def test_run_ingest_with_timeout_returns_once_ingestion_finishes():
    calls = []

    def _fast_ingest(document_id, *, session_factory=None):
        calls.append(document_id)

    document_id = uuid.uuid4()
    _run_ingest_with_timeout(document_id, lambda: None, timeout=5, ingest_fn=_fast_ingest)

    assert calls == [document_id]


def test_run_ingest_with_timeout_aborts_when_ingestion_hangs():
    # Fresh ("created"/"reingested") ingestion previously had no bound at
    # all -- a hung call would block the harness forever (review finding
    # #6). A tiny timeout against a slow fake proves the bound is real.
    def _hanging_ingest(document_id, *, session_factory=None):
        time.sleep(0.5)

    with pytest.raises(EvalHarnessError, match="did not finish"):
        _run_ingest_with_timeout(uuid.uuid4(), lambda: None, timeout=0.05, ingest_fn=_hanging_ingest)


# ---------------------------------------------------------------------------
# Question-set load-time validation (review finding #3)
# ---------------------------------------------------------------------------

_VALID_QUESTION = {
    "id": "q1",
    "category": "factual",
    "question": "Q?",
    "expected_answer": "A.",
    "must_contain": ["A"],
    "match": "all",
    "document_filenames": ["f1.md"],
}


def _write_questions(tmp_path: pathlib.Path, questions) -> pathlib.Path:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(questions), encoding="utf-8")
    return path


def _make_fixtures_dir(tmp_path: pathlib.Path, filenames) -> pathlib.Path:
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    for name in filenames:
        (fixtures_dir / name).write_text("content", encoding="utf-8")
    return fixtures_dir


def test_load_questions_happy_path(tmp_path):
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    path = _write_questions(tmp_path, [_VALID_QUESTION])

    questions = _load_questions(questions_path=path, fixtures_dir=fixtures_dir)

    assert questions == [_VALID_QUESTION]


def test_load_questions_rejects_a_missing_file():
    with pytest.raises(EvalHarnessError, match="Could not load"):
        _load_questions(
            questions_path=pathlib.Path("Z:/does/not/exist.json"), fixtures_dir=pathlib.Path("."),
        )


def test_load_questions_rejects_invalid_json(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(EvalHarnessError, match="Could not load"):
        _load_questions(questions_path=path, fixtures_dir=tmp_path)


def test_load_questions_rejects_a_missing_required_key(tmp_path):
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    bad = dict(_VALID_QUESTION)
    del bad["must_contain"]
    path = _write_questions(tmp_path, [bad])

    with pytest.raises(EvalHarnessError, match="missing required"):
        _load_questions(questions_path=path, fixtures_dir=fixtures_dir)


def test_load_questions_rejects_duplicate_ids(tmp_path):
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    path = _write_questions(tmp_path, [_VALID_QUESTION, _VALID_QUESTION])

    with pytest.raises(EvalHarnessError, match="duplicate"):
        _load_questions(questions_path=path, fixtures_dir=fixtures_dir)


def test_load_questions_rejects_an_invalid_category(tmp_path):
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    bad = dict(_VALID_QUESTION, category="facutal")  # typo
    path = _write_questions(tmp_path, [bad])

    with pytest.raises(EvalHarnessError, match="category"):
        _load_questions(questions_path=path, fixtures_dir=fixtures_dir)


def test_load_questions_rejects_an_invalid_match_mode(tmp_path):
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    bad = dict(_VALID_QUESTION, match="sometimes")
    path = _write_questions(tmp_path, [bad])

    with pytest.raises(EvalHarnessError, match="match mode"):
        _load_questions(questions_path=path, fixtures_dir=fixtures_dir)


@pytest.mark.parametrize("category", ["factual", "synthesis"])
def test_load_questions_rejects_an_empty_must_contain_on_an_answerable_question(tmp_path, category):
    # `all([])` is True, so an empty must_contain would score every answer
    # as correct and silently inflate SM-1 (review finding).
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    bad = dict(_VALID_QUESTION, category=category, must_contain=[])
    path = _write_questions(tmp_path, [bad])

    with pytest.raises(EvalHarnessError, match="empty must_contain"):
        _load_questions(questions_path=path, fixtures_dir=fixtures_dir)


def test_load_questions_allows_an_empty_must_contain_on_an_unanswerable_question(tmp_path):
    # Legitimate there: `classify_unanswerable` never calls `_text_matches`.
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    entry = dict(_VALID_QUESTION, category="unanswerable", must_contain=[], match="any")
    path = _write_questions(tmp_path, [entry])

    assert _load_questions(questions_path=path, fixtures_dir=fixtures_dir) == [entry]


def test_load_questions_rejects_an_unknown_fixture_reference(tmp_path):
    fixtures_dir = _make_fixtures_dir(tmp_path, ["f1.md"])
    bad = dict(_VALID_QUESTION, document_filenames=["does-not-exist.md"])
    path = _write_questions(tmp_path, [bad])

    with pytest.raises(EvalHarnessError, match="doesn't exist"):
        _load_questions(questions_path=path, fixtures_dir=fixtures_dir)


def test_real_eval_questions_json_satisfies_the_spec_ac():
    # AC: "Given the evaluation set, when inspected, then it holds 15-20
    # pairs spanning factual, synthesis, and unanswerable" (review finding
    # #4) -- exercised against the actual checked-in file, not a fixture.
    questions = _load_questions(questions_path=QUESTIONS_PATH, fixtures_dir=FIXTURES_DIR)

    assert 15 <= len(questions) <= 20
    categories = {q["category"] for q in questions}
    assert categories == {"factual", "synthesis", "unanswerable"}
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids))

    # A "synthesis" question whose supporting facts all sit in one document
    # is really a factual one, and silently empties the cross-document
    # category Epic 6 asks the set to span (review finding). This can't
    # prove the join is genuinely required, but it catches the regression
    # where an edit collapses a synthesis question onto a single fixture.
    for question in questions:
        if question["category"] == "synthesis":
            assert len(question["document_filenames"]) >= 2, question["id"]


# ---------------------------------------------------------------------------
# _validate_env (review finding #5)
# ---------------------------------------------------------------------------


def test_validate_env_names_every_missing_var(monkeypatch):
    for name in REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    with pytest.raises(EvalHarnessError) as exc_info:
        _validate_env()

    message = str(exc_info.value)
    for name in REQUIRED_ENV_VARS:
        if name == "DATABASE_URL":
            continue
        assert name in message


def test_validate_env_passes_when_everything_is_set(monkeypatch):
    for name in REQUIRED_ENV_VARS:
        monkeypatch.setenv(name, "x")

    _validate_env()  # does not raise


# ---------------------------------------------------------------------------
# Aggregation math behind SM-1 / SM-2 / SM-C1 (review finding #5)
# ---------------------------------------------------------------------------


def test_percent_computes_a_rounded_percentage():
    assert _percent(3, 4) == "75.0%"
    assert _percent(1, 3) == "33.3%"


def test_percent_handles_a_zero_denominator():
    assert _percent(0, 0) == "n/a (no scored questions)"


def test_print_report_computes_distinct_correct_numerators_and_denominators_per_metric(capsys):
    # Deliberately built so SM-1, SM-2, and SM-C1 land on three different
    # percentages -- a swapped numerator/denominator between metrics would
    # be caught here, not just a coincidentally-matching number.
    results = [
        _result("a1", "factual", "correct"),
        _result("a2", "synthesis", "correct"),
        _result("a3", "factual", "incorrect"),
        _result("a4", "synthesis", "incorrect", is_refusal=True),
        _result("a5", "factual", "error", detail="503: boom"),
        _result("u1", "unanswerable", "refusal", is_refusal=True),
        _result("u2", "unanswerable", "refusal", is_refusal=True),
        _result("u3", "unanswerable", "no_answer"),
        _result("u4", "unanswerable", "violation"),
        _result("u5", "unanswerable", "error", detail="503: boom"),
    ]

    _print_report(
        results, model_id="test-model", started_at=datetime(2026, 8, 17, tzinfo=timezone.utc)
    )

    out = capsys.readouterr().out
    # SM-1: 2 correct / 4 answerable_scored (a5 excluded as an error) = 50.0%
    assert "SM-1 answer accuracy (answerable questions): 50.0% (2/4 correct, 1 excluded as run errors)" in out
    # SM-2: 2 refusals / 4 unanswerable_scored (u5 excluded as an error) = 50.0%
    assert "SM-2 unanswerable-question refusal rate: 50.0% (2/4 refused, 1 excluded as run errors)" in out
    assert "no_answer (benign, not a violation): 1/4" in out
    assert "SM-2 VIOLATION" in out and "u4" in out
    # SM-C1: 1 wrongly-refused / 4 answerable_scored = 25.0% -- distinct
    # from both numbers above, so a metric mix-up would fail this assert.
    assert (
        "SM-C1 answerable-question refusal rate (over-refusal counter-metric): 25.0% "
        "(1/4 answerable questions wrongly refused)" in out
    )
    assert "Run errors (generate_answer 503, excluded from every metric above): 2" in out
    assert "test-model" in out
    assert "2026-08-17T00:00:00+00:00" in out
    # Provenance: both refusal metrics are a direct function of these two
    # knobs, so two runs taken across a threshold change must not look
    # comparable in the output (review finding).
    assert f"Relevance threshold: {RELEVANCE_THRESHOLD}" in out
    assert f"Top-K passages: {TOP_K_PASSAGES}" in out


def test_print_report_reports_zero_sm2_violations_when_none_occurred(capsys):
    results = [
        _result("u1", "unanswerable", "refusal", is_refusal=True),
    ]

    _print_report(results, model_id="m", started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    out = capsys.readouterr().out
    assert "SM-2 violations: 0" in out
