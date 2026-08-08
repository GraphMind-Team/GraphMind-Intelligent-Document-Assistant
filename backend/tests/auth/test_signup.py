import uuid

from sqlalchemy import select

from auth.models import User
from db import engine


def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:12]}@example.com"


async def test_signup_success(client, cleanup_users):
    email = unique_email()
    cleanup_users.append(email)

    response = await client.post(
        "/auth/signup", json={"email": email, "password": "testpass123"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert "id" in body
    assert "created_at" in body
    assert "password" not in body
    assert "password_hash" not in body


async def test_signup_persists_bcrypt_hash_not_plaintext(client, cleanup_users):
    email = unique_email()
    password = "testpass123"
    cleanup_users.append(email)

    await client.post("/auth/signup", json={"email": email, "password": password})

    async with engine.connect() as conn:
        result = await conn.execute(
            select(User.password_hash).where(User.email == email)
        )
        stored_hash = result.scalar_one()

    assert stored_hash != password
    assert stored_hash.startswith("$2b$")


async def test_signup_duplicate_email_rejected(client, cleanup_users):
    email = unique_email()
    cleanup_users.append(email)

    first = await client.post(
        "/auth/signup", json={"email": email, "password": "testpass123"}
    )
    assert first.status_code == 201

    second = await client.post(
        "/auth/signup", json={"email": email, "password": "differentpass456"}
    )
    assert second.status_code == 409


async def test_signup_invalid_email_rejected(client):
    response = await client.post(
        "/auth/signup", json={"email": "not-an-email", "password": "testpass123"}
    )
    assert response.status_code == 422


async def test_signup_password_too_short_rejected(client):
    response = await client.post(
        "/auth/signup", json={"email": unique_email(), "password": "short"}
    )
    assert response.status_code == 422
