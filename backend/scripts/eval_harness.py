"""Story 6.1: single-command evaluation harness for answer accuracy and
refusal correctness.

Ingests a small git-tracked fixture corpus (`scripts/eval_fixtures/*.md`)
into the QA account, runs a 15-20 question set
(`scripts/eval_questions.json`, spanning factual / synthesis /
unanswerable) through `chat.service.ask_question` scoped to those
fixtures' document ids -- never HTTP, never the frontend -- and prints
accuracy, unanswerable-refusal-rate, and answerable-refusal-rate (SM-C1)
as plain numbers. Never pass/fail: quality is reported, not gated (see
this module's own report -- and the spec's Ask First note about not
silently rewriting OD-3/SM-1 off of one run).

Runs against the real Weaviate/Neo4j/OpenRouter/Postgres configured in
`backend/.env` -- this is the project's Definition-of-Done gate, so a
mocked LLM or vector store would defeat its own purpose. Missing
configuration fails loudly (`_validate_env`), not silently.

Scoring note: each question's `must_contain`/`match` fields are what's
actually graded (`classify_answerable`/`classify_unanswerable`, via
`_text_matches`) -- `expected_answer` is documentation only, read by a
human editing the question set, never by this script. Keep them in sync
by hand; nothing here checks that they still agree after an edit.

Known limitation (not fixed here, out of scope for this harness):
`upload_document`'s content-hash dedup means editing any
`eval_fixtures/*.md` file after a prior run creates a *new* document row
under the QA account rather than replacing the old one -- there is no
cleanup step, so the QA account's document library grows across repeated
runs of an edited fixture set. See `_print_report`'s footer, which
restates this at the end of every run.

Usage (run from `backend/`, same convention as
`scripts/rebuild_graph_with_provenance.py`):

    python -m scripts.eval_harness
"""

import argparse
import json
import logging
import os
import pathlib
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, get_args

from fastapi import HTTPException

from app.auth.repository import get_user_by_email
from app.chat.schemas import AskResponse
from app.chat.service import ask_question
from app.documents import service as documents_service
from app.shared.data_access.session import get_session_factory
from app.shared.llm_client import DEFAULT_MODEL
from app.shared.models import Document, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The one and only QA account this harness ever runs against (spec
# Boundaries: "Reuse the QA account -- no throwaway accounts"). Must
# already exist in the target Postgres database; this script never
# registers it. Overridable via env var rather than only a source literal,
# so a different environment/account can be pointed at without editing
# code (review finding: no override existed before).
QA_ACCOUNT_EMAIL = os.environ.get("EVAL_QA_ACCOUNT_EMAIL", "essinkabg@gmail.com")

_SCRIPT_DIR = pathlib.Path(__file__).parent
FIXTURES_DIR = _SCRIPT_DIR / "eval_fixtures"
QUESTIONS_PATH = _SCRIPT_DIR / "eval_questions.json"

# The DoD gate this harness exists to prove -- every one of these backs a
# real call `ask_question`/`ingest_document` makes below. Checked up front
# with a single clear message rather than letting each ingest/ask call fail
# with its own scattered RuntimeError partway through the run.
REQUIRED_ENV_VARS = [
    "DATABASE_URL",
    "WEAVIATE_URL",
    "WEAVIATE_API_KEY",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "OPENROUTER_API_KEY",
]

# How long to wait for a single fixture to reach a terminal status --
# whether it's a fresh ingestion this run just started, or one found mid-
# pipeline from an interrupted earlier run. Both paths route through this
# same bound (`_run_ingest_with_timeout`/`_poll_until_terminal`) so neither
# can block the harness forever.
_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 300.0

_READY_STATUS = "Ready"
_FAILED_STATUS = "Failed"

_FIXTURE_CONTENT_TYPE = "text/markdown"

Category = Literal["factual", "synthesis", "unanswerable"]
_VALID_CATEGORIES = frozenset(get_args(Category))

MatchMode = Literal["all", "any"]
_VALID_MATCH_MODES = frozenset(get_args(MatchMode))

_REQUIRED_QUESTION_KEYS = frozenset(
    {"id", "category", "question", "expected_answer", "must_contain", "match", "document_filenames"}
)


class EvalHarnessError(Exception):
    """An abort condition the spec calls out explicitly: missing env vars,
    a fixture that failed or is stuck mid-pipeline, a malformed question
    set, or a scoping bug. Never caught internally -- propagates out of
    `main()` to a clear stderr message and a nonzero exit. Deliberately
    distinct from a per-question run error (a failure raised by
    `ask_question` itself -- a 503, or any other transient
    Weaviate/Neo4j/OpenRouter failure), which `_run_question` logs and
    turns into a `status="error"` result rather than aborting the run."""


class ScopeError(EvalHarnessError):
    """Raised when `ask_question` returns `empty_reason` in
    `("no_documents", "empty_scope")`. The harness always passes a
    non-empty list of real fixture document ids (spec Boundaries: "never
    []"), so either of these means the scoping itself is broken -- not a
    real accuracy/refusal outcome to score. Aborts the run rather than
    silently folding a scoping bug into the metrics."""


# ---------------------------------------------------------------------------
# Environment / fixture ingestion
# ---------------------------------------------------------------------------


def _validate_env() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise EvalHarnessError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. See backend/.env.example. This harness runs against "
            "real Weaviate/Neo4j/OpenRouter/Postgres by design (it's the project's DoD "
            "gate) -- there is no mocked fallback."
        )


def _resolve_qa_user(db) -> User:
    user = get_user_by_email(db, QA_ACCOUNT_EMAIL)
    if user is None:
        raise EvalHarnessError(
            f"QA account {QA_ACCOUNT_EMAIL!r} does not exist in this database. Register it "
            "first -- this harness reuses the existing QA account and never creates one."
        )
    return user


def _decide_fixture_action(
    outcome: str, status: str
) -> Literal["ingest", "reuse", "poll_or_abort"]:
    """Given `upload_document`'s outcome and the resulting row's current
    `status`, decides what `_ingest_fixture` does next. Pure and
    side-effect-free -- no DB/Weaviate/Neo4j/OpenRouter call -- so this is
    unit-testable on its own (spec Tasks: "one case per I/O-matrix row",
    the "Re-running the harness" row).

    "created"/"reingested" always need a fresh `ingest_document` call --
    `upload_document` just wrote/reset the row to "Uploaded" and this
    standalone script has no `BackgroundTasks` to schedule it for us.

    "duplicate" reuses the existing row untouched. If it's already
    "Ready", there's nothing left to do. Otherwise it's sitting in a
    non-terminal status this harness run didn't just put it in --
    Extracting/Graphing/Uploaded left over from an interrupted earlier
    run (`ingest_document`'s own documented no-safety-net gap: a hard
    process crash mid-task leaves a row stuck with nothing to unlock it).
    Silently calling `ingest_document` on it again would race a second
    pipeline against whatever already touched it -- the spec's Never
    clause forbids exactly that -- so this polls for it to reach a
    terminal state instead, and the caller aborts if it never does.

    Raises `EvalHarnessError` (not a bare `ValueError`) for an
    unrecognized `outcome` -- `upload_document`'s own `UploadOutcome`
    contract only names three values, so anything else reaching here is a
    real bug worth a clean abort message rather than a raw traceback.
    """
    if outcome in ("created", "reingested"):
        return "ingest"
    if outcome == "duplicate":
        return "reuse" if status == _READY_STATUS else "poll_or_abort"
    raise EvalHarnessError(
        f"upload_document returned an unrecognized outcome {outcome!r} -- expected one of "
        "'created', 'duplicate', 'reingested'."
    )


def _poll_until_terminal(
    db,
    document_id,
    *,
    timeout: float = _POLL_TIMEOUT_SECONDS,
    interval: float = _POLL_INTERVAL_SECONDS,
    sleep=time.sleep,
    now=time.monotonic,
) -> Document:
    """Re-fetches `document_id` until its status is `Ready`/`Failed` or
    `timeout` elapses. `sleep`/`now` are injectable purely so a test can
    exercise the timeout branch without a real wall-clock wait."""
    deadline = now() + timeout
    while True:
        db.expire_all()
        document = db.get(Document, document_id)
        if document is None:
            raise EvalHarnessError(f"Fixture document {document_id} disappeared while polling.")
        if document.status in (_READY_STATUS, _FAILED_STATUS):
            return document
        if now() >= deadline:
            raise EvalHarnessError(
                f"Timed out after {timeout}s waiting for document {document_id} to leave "
                f"status={document.status!r}. It's likely stuck from an interrupted earlier "
                "run (Story 2.3's no-safety-net gap) -- resolve manually before re-running."
            )
        sleep(interval)


def _run_ingest_with_timeout(
    document_id: uuid.UUID,
    session_factory,
    *,
    timeout: float = _POLL_TIMEOUT_SECONDS,
    ingest_fn=documents_service.ingest_document,
) -> None:
    """Runs `ingest_fn` (`ingest_document` by default -- injectable so a
    test can exercise the timeout branch without a real hang) in a
    background thread and waits up to `timeout` seconds for it to finish.

    `ingest_document` itself has no overall wall-clock deadline of its
    own -- only the individual HTTP calls inside `shared/llm_client` are
    bounded. Without this wrapper, a fresh ("created"/"reingested")
    fixture ingestion that somehow wedges (e.g. a hung TCP connection
    below httpx's own timeout layer) would block this script forever,
    unlike the "duplicate, not Ready" path, which already had a bound via
    `_poll_until_terminal`. This gives both paths the identical
    never-block-forever guarantee.

    The thread is a daemon and is never explicitly stopped on timeout --
    Python has no safe way to kill another thread mid-call. On timeout,
    this raises and the harness aborts; the orphaned thread (and whatever
    DB/Weaviate/Neo4j write it's mid-way through) may keep running in the
    background of the now-exiting process. That's an accepted, documented
    trade-off for a script whose alternative is blocking forever with no
    way out at all.
    """
    thread = threading.Thread(
        target=ingest_fn,
        args=(document_id,),
        kwargs={"session_factory": session_factory},
        daemon=True,
    )
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise EvalHarnessError(
            f"Ingestion for document {document_id} did not finish within {timeout}s -- "
            "aborting rather than blocking forever. It may still be running in the "
            "background; check the row's status manually before re-running."
        )


def _ingest_fixture(db, session_factory, user: User, fixture_path: pathlib.Path) -> Document:
    """Uploads and ensures one fixture reaches `Ready`, per
    `_decide_fixture_action`'s decision. Raises `EvalHarnessError` if the
    fixture ends up `Failed`, is stuck in a non-terminal status, or fails
    upload validation (format/size) -- `validate_format`/`validate_size`
    raise `HTTPException` (the route-layer contract), which is never a
    shape this standalone script's caller should have to handle as a raw
    exception."""
    filename = fixture_path.name
    content = fixture_path.read_bytes()

    try:
        file_type = documents_service.validate_format(filename, _FIXTURE_CONTENT_TYPE)
        documents_service.validate_size(len(content))
        document, outcome = documents_service.upload_document(
            db, user, filename=filename, file_type=file_type, content=content
        )
    except HTTPException as exc:
        raise EvalHarnessError(
            f"Fixture {filename!r} failed upload validation ({exc.status_code}): {exc.detail}"
        ) from exc
    logger.info("Fixture %s: upload outcome=%s (document_id=%s)", filename, outcome, document.id)

    action = _decide_fixture_action(outcome, document.status)
    if action == "ingest":
        _run_ingest_with_timeout(document.id, session_factory)
        db.expire(document)
    elif action == "poll_or_abort":
        logger.warning(
            "Fixture %s: existing duplicate found in status=%s -- polling for it to reach a "
            "terminal state rather than re-driving ingestion.",
            filename,
            document.status,
        )
        document = _poll_until_terminal(db, document.id)
    # "reuse": already Ready, nothing to do.

    db.refresh(document)
    if document.status == _FAILED_STATUS:
        raise EvalHarnessError(
            f"Fixture {filename!r} (document_id={document.id}) failed ingestion: "
            f"{document.failed_reason}"
        )
    if document.status != _READY_STATUS:
        raise EvalHarnessError(
            f"Fixture {filename!r} (document_id={document.id}) is stuck at "
            f"status={document.status!r} instead of reaching Ready. Resolve manually before "
            "re-running the harness."
        )
    return document


def _ingest_all_fixtures(db, session_factory, user: User) -> dict[str, uuid.UUID]:
    """Uploads/ingests every fixture and returns `filename -> document_id`
    -- plain `uuid.UUID`s, deliberately not the `Document` ORM objects
    themselves. The per-question loop (`_run`) opens its own short-lived
    session per question rather than holding `db` open for the whole
    LLM-backed run; carrying a detached ORM object across that session
    boundary risks `DetachedInstanceError` on any attribute SQLAlchemy
    considers expired (e.g. after any `commit()` on this session, which
    `upload_document`/`ingest_document` both call). A plain UUID has no
    such lifetime coupling."""
    fixture_paths = sorted(FIXTURES_DIR.glob("*.md"))
    if not fixture_paths:
        raise EvalHarnessError(f"No fixture files found under {FIXTURES_DIR}.")
    document_ids: dict[str, uuid.UUID] = {}
    for fixture_path in fixture_paths:
        document = _ingest_fixture(db, session_factory, user, fixture_path)
        document_ids[fixture_path.name] = document.id
    return document_ids


# ---------------------------------------------------------------------------
# Question set
# ---------------------------------------------------------------------------


def _load_questions(
    *, questions_path: pathlib.Path = QUESTIONS_PATH, fixtures_dir: pathlib.Path = FIXTURES_DIR
) -> list[dict]:
    """Loads and validates `eval_questions.json`. Schema/shape checks
    happen here, once, at load time -- so a malformed or hand-edited
    question set (a missing key, a typo'd category that would otherwise
    silently fall through and get scored as answerable, a duplicate id, a
    `document_filenames` entry with no matching fixture file) fails
    loudly before any live Weaviate/Neo4j/OpenRouter call is made, rather
    than corrupting a run partway through or producing a quietly wrong
    metric. `questions_path`/`fixtures_dir` are overridable purely so
    tests can exercise this against temp files instead of the real ones.

    Reminder for whoever edits this file: `must_contain`/`match` are what
    actually drive scoring (see `classify_answerable`); `expected_answer`
    is documentation only and isn't checked against the other two here.
    """
    try:
        with open(questions_path, encoding="utf-8") as f:
            questions = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalHarnessError(f"Could not load {questions_path}: {exc}") from exc

    if not isinstance(questions, list) or not questions:
        raise EvalHarnessError(f"{questions_path} must contain a non-empty JSON array of questions.")

    fixture_filenames = {p.name for p in fixtures_dir.glob("*.md")}
    seen_ids: set[str] = set()
    for entry in questions:
        if not isinstance(entry, dict):
            raise EvalHarnessError(f"{questions_path}: every question must be a JSON object, got {entry!r}.")

        missing_keys = _REQUIRED_QUESTION_KEYS - entry.keys()
        if missing_keys:
            raise EvalHarnessError(
                f"{questions_path}: question {entry.get('id', '<no id>')!r} is missing required "
                f"key(s): {sorted(missing_keys)}."
            )

        qid = entry["id"]
        if qid in seen_ids:
            raise EvalHarnessError(f"{questions_path}: duplicate question id {qid!r}.")
        seen_ids.add(qid)

        if entry["category"] not in _VALID_CATEGORIES:
            raise EvalHarnessError(
                f"{questions_path}: question {qid!r} has an invalid category {entry['category']!r} "
                f"(must be one of {sorted(_VALID_CATEGORIES)})."
            )

        if entry["match"] not in _VALID_MATCH_MODES:
            raise EvalHarnessError(
                f"{questions_path}: question {qid!r} has an invalid match mode {entry['match']!r} "
                f"(must be one of {sorted(_VALID_MATCH_MODES)})."
            )

        for filename in entry["document_filenames"]:
            if filename not in fixture_filenames:
                raise EvalHarnessError(
                    f"{questions_path}: question {qid!r} references fixture {filename!r}, which "
                    f"doesn't exist under {fixtures_dir}."
                )

    return questions


# ---------------------------------------------------------------------------
# Scoring / classification (per the spec's I/O & Edge-Case Matrix)
# ---------------------------------------------------------------------------


def _text_matches(text: str, must_contain: list[str], match: str) -> bool:
    """Case-insensitive substring match against the answer's concatenated
    segment text -- deterministic scoring per the spec's Design Notes.
    This is the only thing that determines "correct"/"incorrect";
    `expected_answer` (in `eval_questions.json`) is documentation only and
    is never read here.

    Raises `EvalHarnessError` (not a bare `ValueError`) for an
    unrecognized `match` mode -- `_load_questions` already rejects this at
    load time for the real question set, but this stays defensive for any
    other caller."""
    haystack = text.lower()
    hits = [needle.lower() in haystack for needle in must_contain]
    if match == "all":
        return all(hits)
    if match == "any":
        return any(hits)
    raise EvalHarnessError(f"Unknown match mode: {match!r} (expected one of {sorted(_VALID_MATCH_MODES)}).")


def classify_answerable(question: dict, response: AskResponse) -> tuple[str, bool]:
    """Scores a factual/synthesis question. Returns `(verdict, is_refusal)`
    where `verdict` is `"correct"` or `"incorrect"`, and `is_refusal` is
    `True` iff `response.empty_reason == "refusal"` -- the only case that
    feeds SM-C1's (answerable-refusal-rate) numerator. Per the spec's
    Boundaries, `no_answer`/`no_documents`/`empty_scope` are distinct from
    a refusal and never counted as one, even though `no_answer` still
    scores incorrect for accuracy.

    Raises `ScopeError` for `no_documents`/`empty_scope` -- the harness
    always scopes to non-empty real fixture ids, so either means the
    scoping itself is broken, not a real outcome to score.
    """
    if response.empty_reason in ("no_documents", "empty_scope"):
        raise ScopeError(
            f"Question {question['id']!r} got empty_reason={response.empty_reason!r} against "
            "fixture-scoped document_ids -- this should never happen; aborting rather than "
            "silently scoring a scoping bug."
        )
    if response.empty_reason == "refusal":
        # Incorrect for SM-1 *and* feeds SM-C1's numerator -- the exact
        # case that metric exists to catch (spec I/O matrix).
        return "incorrect", True
    if response.empty_reason == "no_answer":
        return "incorrect", False
    text = " ".join(segment.text for segment in response.segments)
    matched = _text_matches(text, question["must_contain"], question["match"])
    return ("correct" if matched else "incorrect"), False


def classify_unanswerable(question: dict, response: AskResponse) -> str:
    """Scores an unanswerable question. Returns `"refusal"` (correct/
    desired), `"no_answer"` (benign -- logged separately, not an SM-2
    violation per the spec), or `"violation"` (the model actually
    answered a question none of the fixtures support -- an SM-2
    violation). Raises `ScopeError` for `no_documents`/`empty_scope`, same
    reasoning as `classify_answerable`."""
    if response.empty_reason in ("no_documents", "empty_scope"):
        raise ScopeError(
            f"Question {question['id']!r} got empty_reason={response.empty_reason!r} against "
            "fixture-scoped document_ids -- this should never happen; aborting rather than "
            "silently scoring a scoping bug."
        )
    if response.empty_reason == "refusal":
        return "refusal"
    if response.empty_reason == "no_answer":
        return "no_answer"
    return "violation"


@dataclass(frozen=True)
class QuestionRunResult:
    question_id: str
    category: Category
    # "correct"/"incorrect" (answerable), "refusal"/"no_answer"/"violation"
    # (unanswerable), or "error" (ask_question failed -- excluded from
    # every metric below).
    status: str
    is_refusal: bool = False
    detail: str = ""


def _run_question(
    db,
    user: User,
    question: dict,
    document_ids_by_filename: dict[str, uuid.UUID],
    *,
    ask_fn=ask_question,
) -> QuestionRunResult:
    """Runs one question through `ask_fn` (`ask_question` by default --
    injectable so tests can fake it without a live LLM/Weaviate/Neo4j) and
    classifies the result.

    Any exception raised by `ask_fn` itself -- a `generate_answer` 503
    (surfaced as `HTTPException(503, ...)`, `ask_question`'s one
    documented exception path), any other `HTTPException`, or a
    lower-level transient failure (a Weaviate/Neo4j connection error, a
    timeout) -- is logged and recorded as a `status="error"` result,
    excluded from every metric, rather than aborting the whole run. One
    flaky call must not erase every other question's already-completed
    result (review finding). Never scored as a refusal (spec Never
    clause), regardless of which exception type it was.

    A `KeyError` while resolving `document_filenames` against the
    ingested fixtures is a different kind of failure -- a data-integrity
    bug in `eval_questions.json` vs. the actual fixture corpus, not a
    live-service flake -- so it's translated into a clear
    `EvalHarnessError` and allowed to abort the run, same as any other
    setup-time problem.
    """
    try:
        document_ids = [document_ids_by_filename[fn] for fn in question["document_filenames"]]
    except KeyError as exc:
        raise EvalHarnessError(
            f"Question {question['id']!r} references fixture {exc.args[0]!r}, which isn't among "
            f"the ingested fixtures ({sorted(document_ids_by_filename)})."
        ) from exc

    try:
        response = ask_fn(db, user, question["question"], document_ids)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            detail = f"{exc.status_code}: {exc.detail}"
        else:
            detail = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "Question %s: ask_question failed -- recording as a run error and continuing",
            question["id"],
        )
        return QuestionRunResult(
            question_id=question["id"],
            category=question["category"],
            status="error",
            detail=detail,
        )

    if question["category"] == "unanswerable":
        verdict = classify_unanswerable(question, response)
        return QuestionRunResult(
            question_id=question["id"],
            category="unanswerable",
            status=verdict,
            is_refusal=(verdict == "refusal"),
        )

    verdict, is_refusal = classify_answerable(question, response)
    return QuestionRunResult(
        question_id=question["id"],
        category=question["category"],
        status=verdict,
        is_refusal=is_refusal,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a (no scored questions)"
    return f"{100.0 * numerator / denominator:.1f}%"


def _print_report(results: list[QuestionRunResult], *, model_id: str, started_at: datetime) -> None:
    answerable = [r for r in results if r.category in ("factual", "synthesis")]
    unanswerable = [r for r in results if r.category == "unanswerable"]

    answerable_errors = [r for r in answerable if r.status == "error"]
    answerable_scored = [r for r in answerable if r.status != "error"]
    answerable_correct = [r for r in answerable_scored if r.status == "correct"]
    answerable_refusals = [r for r in answerable_scored if r.is_refusal]

    unanswerable_errors = [r for r in unanswerable if r.status == "error"]
    unanswerable_scored = [r for r in unanswerable if r.status != "error"]
    unanswerable_refusals = [r for r in unanswerable_scored if r.status == "refusal"]
    unanswerable_no_answer = [r for r in unanswerable_scored if r.status == "no_answer"]
    unanswerable_violations = [r for r in unanswerable_scored if r.status == "violation"]

    total_errors = len(answerable_errors) + len(unanswerable_errors)

    print("=" * 78)
    print("GraphMind Evaluation Harness -- Story 6.1")
    print(f"Model:        {model_id}")
    print(f"Run started:  {started_at.isoformat()}")
    print(f"Question count: {len(results)} ({len(answerable)} answerable, "
          f"{len(unanswerable)} unanswerable)")
    print("=" * 78)

    accuracy_pct = _percent(len(answerable_correct), len(answerable_scored))
    print(
        f"\nSM-1 answer accuracy (answerable questions): {accuracy_pct} "
        f"({len(answerable_correct)}/{len(answerable_scored)} correct, "
        f"{len(answerable_errors)} excluded as run errors)"
    )
    print(
        "  -> This is the measured baseline for OD-3's placeholder >=80% SM-1 target. "
        "Report this number to a human to resolve OD-3 -- do not edit epics.md here."
    )

    refusal_pct = _percent(len(unanswerable_refusals), len(unanswerable_scored))
    print(
        f"\nSM-2 unanswerable-question refusal rate: {refusal_pct} "
        f"({len(unanswerable_refusals)}/{len(unanswerable_scored)} refused, "
        f"{len(unanswerable_errors)} excluded as run errors)"
    )
    print(
        f"  no_answer (benign, not a violation): {len(unanswerable_no_answer)}/{len(unanswerable_scored)}"
    )
    if unanswerable_violations:
        print(
            f"  SM-2 VIOLATION -- actually answered {len(unanswerable_violations)} unanswerable "
            f"question(s): {', '.join(r.question_id for r in unanswerable_violations)}"
        )
    else:
        print("  SM-2 violations: 0")

    sm_c1_pct = _percent(len(answerable_refusals), len(answerable_scored))
    print(
        f"\nSM-C1 answerable-question refusal rate (over-refusal counter-metric): {sm_c1_pct} "
        f"({len(answerable_refusals)}/{len(answerable_scored)} answerable questions wrongly refused)"
    )

    print(f"\nRun errors (generate_answer 503, excluded from every metric above): {total_errors}")
    for r in answerable_errors + unanswerable_errors:
        print(f"  {r.question_id} ({r.category}): {r.detail}")

    print(
        "\nNote: fixture content-hash dedup means an edited eval_fixtures/*.md file becomes a "
        "*new* document row on the next run rather than replacing the old one -- the QA "
        "account's document library grows across repeated runs of an edited fixture set. No "
        "automatic cleanup exists (documentation-only limitation, out of scope for this harness)."
    )

    print("=" * 78)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _run() -> None:
    started_at = datetime.now(timezone.utc)
    _validate_env()

    session_factory = get_session_factory()

    # Fixture ingestion (upload + parse + embed + extract + graph-write for
    # up to 3 documents) needs one session for its own short duration.
    setup_db = session_factory()
    try:
        user = _resolve_qa_user(setup_db)
        document_ids_by_filename = _ingest_all_fixtures(setup_db, session_factory, user)
    finally:
        setup_db.close()

    questions = _load_questions()

    # A fresh, short-lived session per question rather than one session
    # held open for the whole ~15-20 question, LLM-backed run (each
    # `ask_question` call can itself take up to ~120s worst case per its
    # own docstring) -- this project's Postgres is Neon (serverless),
    # which can enforce idle-connection limits well under that combined
    # runtime (review finding). `user` is re-resolved per question for the
    # same reason: a `User` fetched on one session becomes a
    # `DetachedInstanceError` risk once that session closes and a
    # (possibly expired) attribute is accessed again -- re-fetching by
    # email is one cheap indexed SELECT, negligible next to the LLM call
    # the same iteration is about to make.
    results: list[QuestionRunResult] = []
    for question in questions:
        logger.info("Running %s [%s]: %s", question["id"], question["category"], question["question"])
        db = session_factory()
        try:
            question_user = _resolve_qa_user(db)
            result = _run_question(db, question_user, question, document_ids_by_filename)
        finally:
            db.close()
        results.append(result)
        logger.info("  -> %s", result.status)

    model_id = os.environ.get("OPENROUTER_CHAT_MODEL", DEFAULT_MODEL)
    _print_report(results, model_id=model_id, started_at=started_at)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        _run()
    except EvalHarnessError as exc:
        # A clean one-line-per-cause abort message, not a traceback -- the
        # abort conditions here (missing env vars, a failed/stuck fixture,
        # a malformed question set, a scoping bug) are expected, actionable
        # operator errors, not bugs in this script.
        print(f"eval_harness: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
