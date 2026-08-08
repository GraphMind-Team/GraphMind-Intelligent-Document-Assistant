import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from auth.models import User
from auth.router import router
from db import engine


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def cleanup_users():
    """Yields a list; tests append emails they create, and this fixture
    deletes those rows from the real Neon DB after the test finishes."""
    emails: list[str] = []
    yield emails
    if emails:
        async with engine.connect() as conn:
            await conn.execute(delete(User).where(User.email.in_(emails)))
            await conn.commit()
