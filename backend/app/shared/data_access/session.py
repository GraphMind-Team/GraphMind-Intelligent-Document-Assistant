"""Postgres engine and session factory.

Per architecture decision AD-2, this is the sole place a SQLAlchemy engine
is constructed -- module `repository.py` files depend on `get_db_session`
rather than opening their own connections.

Calls `load_dotenv()` defensively at import time so this module is safely
importable on its own (e.g. from Alembic or a test) regardless of whether
`app.main` has already loaded `backend/.env` first.

Engine/session-factory construction is deliberately lazy (built on first
use, not at import time): `test_health.py` imports `app.main` -- and
transitively this module -- during pytest collection, before any test can
override `get_db_session`. A module-level engine would silently build a
real connection pool against `DATABASE_URL` (production Neon, locally) on
every test run even though nothing ever queries through it. Fail-fast for
real usage is unaffected: `app.main`'s `_validate_env()` already requires
`DATABASE_URL` at boot, before this module's lazy check would ever fire.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


@lru_cache
def get_engine():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Missing required environment variable: DATABASE_URL. See backend/.env.example."
        )
    # pool_pre_ping guards against Neon's serverless Postgres dropping idle
    # connections -- without it, a stale connection surfaces as a random 500.
    return create_engine(database_url, pool_pre_ping=True)
    # NOTE: once a real test Postgres exists (Story 1.5 / CI), tests that
    # need it must call get_engine.cache_clear() between runs if
    # DATABASE_URL changes mid-process, since this is memoized.


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db_session() -> Session:
    """FastAPI dependency yielding a request-scoped DB session."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
