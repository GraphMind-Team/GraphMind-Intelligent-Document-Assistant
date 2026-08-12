"""Sets required env vars before `app.main` is imported by any test.

`app.main` validates required env vars at import time (fail-fast on boot).
That means importing it for tests needs the same vars present first --
done here via `monkeypatch.setenv` in an autouse, session-scoped fixture
so individual test modules never have to think about it.
"""

import pytest


@pytest.fixture(autouse=True, scope="session")
def _required_env_vars():
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    os.environ.setdefault("JWT_SECRET", "test-secret")
    yield
