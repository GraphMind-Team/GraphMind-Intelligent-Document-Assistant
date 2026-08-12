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
def _fresh_auth_rate_limiters(client):
    """Overrides both module-level rate-limiter singletons (login, register)
    with fresh instances per test, so attempt counts from one test -- or
    from an earlier test file in the same run -- never leak into the next.
    Depends on `client` (not standalone) so it composes correctly with the
    `client` fixture above, which clears `app.dependency_overrides` in its
    own `finally` block on teardown. Autouse + defined here (not per test
    file) because every test that hits `/auth/register` or `/auth/login`
    -- not just the rate-limit-specific tests -- would otherwise share one
    process-wide budget across the whole test run."""
    from app.auth.rate_limiter import RateLimiter, get_login_rate_limiter, get_register_rate_limiter
    from app.main import app

    login_limiter = RateLimiter(
        max_attempts=5, window_seconds=60.0, detail="Too many login attempts. Try again later."
    )
    register_limiter = RateLimiter(
        max_attempts=5, window_seconds=60.0, detail="Too many registration attempts. Try again later."
    )
    app.dependency_overrides[get_login_rate_limiter] = lambda: login_limiter
    app.dependency_overrides[get_register_rate_limiter] = lambda: register_limiter
    yield login_limiter, register_limiter
    app.dependency_overrides.pop(get_login_rate_limiter, None)
    app.dependency_overrides.pop(get_register_rate_limiter, None)
