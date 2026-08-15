"""Sets required env vars before `app.main` is imported by any test.

`app.main` validates required env vars at import time (fail-fast on boot),
and `test_health.py` imports `app.main` at module level -- which happens
during pytest *collection*, before any fixture runs (fixtures only run
once collection is complete). So these fallbacks are set here at module
*import* time instead of in a fixture: pytest guarantees `conftest.py`
imports before it collects test modules in the same directory tree, which
is early enough. Do not move this back into a fixture -- it would silently
stop protecting `test_health.py` on a machine/CI runner with no
`backend/.env`.

Because `load_dotenv()` (called by both `app.main` and
`app.shared.data_access.session`) does not override variables already
present in `os.environ`, setting these here first also means the real
`DATABASE_URL` from `backend/.env` never becomes visible to the test
process at all -- not just unused.
"""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long-for-hs256")


@pytest.fixture()
def db_session():
    """A fresh in-memory SQLite DB per test.

    SQLite instead of the real Neon DB (there is no separate test Postgres
    instance in this environment) -- works because `User.id` uses
    SQLAlchemy's dialect-agnostic `Uuid` type rather than a Postgres-only
    default. `StaticPool` keeps the single in-memory connection alive for
    the fixture's lifetime instead of it disappearing between uses.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.shared.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """A TestClient with `get_db_session` overridden to the SQLite fixture."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.shared.data_access import get_db_session

    def _override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fresh_rate_limiters(client):
    """Overrides every module-level limiter singleton (login, register,
    upload rate, upload concurrency) with fresh instances per test, so
    counts from one test -- or from an earlier test file in the same run
    -- never leak into the next. Depends on `client` (not standalone) so
    it composes correctly with the `client` fixture above, which clears
    `app.dependency_overrides` in its own `finally` block on teardown.
    Autouse + defined here (not per test file) because every test that
    hits `/auth/register`, `/auth/login`, or `POST /documents` -- not just
    the limit-specific tests -- would otherwise share one process-wide
    budget across the whole test run."""
    from app.auth.rate_limiter import (
        get_change_password_rate_limiter,
        get_login_rate_limiter,
        get_register_rate_limiter,
    )
    from app.documents.rate_limiter import (
        get_upload_concurrency_limiter,
        get_upload_rate_limiter,
    )
    from app.main import app
    from app.shared.rate_limiter import ConcurrencyLimiter, RateLimiter

    login_limiter = RateLimiter(
        max_attempts=5, window_seconds=60.0, detail="Too many login attempts. Try again later."
    )
    register_limiter = RateLimiter(
        max_attempts=5, window_seconds=60.0, detail="Too many registration attempts. Try again later."
    )
    change_password_limiter = RateLimiter(
        max_attempts=5,
        window_seconds=60.0,
        detail="Too many password change attempts. Try again later.",
    )
    upload_rate_limiter = RateLimiter(
        max_attempts=30, window_seconds=60.0, detail="Too many uploads. Try again in a minute."
    )
    upload_concurrency_limiter = ConcurrencyLimiter(max_concurrent=5)

    app.dependency_overrides[get_login_rate_limiter] = lambda: login_limiter
    app.dependency_overrides[get_register_rate_limiter] = lambda: register_limiter
    app.dependency_overrides[get_change_password_rate_limiter] = lambda: change_password_limiter
    app.dependency_overrides[get_upload_rate_limiter] = lambda: upload_rate_limiter
    app.dependency_overrides[get_upload_concurrency_limiter] = lambda: upload_concurrency_limiter
    yield login_limiter, register_limiter, change_password_limiter, upload_rate_limiter, upload_concurrency_limiter
    for dependency in (
        get_login_rate_limiter,
        get_register_rate_limiter,
        get_change_password_rate_limiter,
        get_upload_rate_limiter,
        get_upload_concurrency_limiter,
    ):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture(autouse=True)
def _stub_ingestion_pipeline(monkeypatch):
    """Every document upload now schedules `service.ingest_document` as a
    background task (Story 2.3). `TestClient` runs background tasks
    synchronously to completion before `client.post(...)` returns, so left
    un-stubbed, EVERY test that uploads a document -- not just this
    story's own -- would exercise real parsing/embedding/Weaviate-writing,
    and would move `status` off `"Uploaded"` (breaking pre-2.3 tests that
    assert the row stays `Uploaded` after upload).

    Route-triggered ingestion is a no-op `Mock` by default: pre-2.3 tests
    keep their original "nothing happens after upload" behavior with no
    changes of their own needed. The dedicated ingestion test file
    (`test_documents_parse_and_index.py`) imports `service.ingest_document`
    at module load time -- a plain name binding, captured before this
    per-test patch ever runs -- and calls that real function directly with
    its own `session_factory`, bypassing `BackgroundTasks` (and this stub)
    entirely rather than trying to un-mock a shared global.
    """
    from unittest.mock import Mock

    from app.documents import service

    fake_ingest_document = Mock()
    monkeypatch.setattr(service, "ingest_document", fake_ingest_document)
    return fake_ingest_document
