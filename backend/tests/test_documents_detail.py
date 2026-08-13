"""`GET /documents/{document_id}` tests (Story 2.2).

This is the codebase's first by-id document endpoint, so its first IDOR
surface -- the cross-tenant case below is the load-bearing test in this
file: it pins *404, not 403*, because a 403 would confirm that the id
exists and belongs to someone. It also asserts the response body carries
nothing about the other account's document at all.
"""

import uuid


def _register_and_login(client, *, full_name, email, password):
    register_response = client.post(
        "/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _upload(client, token, filename="report.pdf", content_type="application/pdf"):
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": (filename, b"%PDF-1.4 fake pdf bytes", content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_get_returns_the_callers_own_document(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-detail@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="quarterly-report.pdf")

    response = client.get(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == uploaded["id"]
    assert body["filename"] == "quarterly-report.pdf"
    assert body["file_type"] == "pdf"
    assert body["status"] == "Uploaded"
    assert body["file_size_bytes"] > 0
    assert "created_at" in body


def test_get_never_serializes_raw_content_or_owner(client):
    """`DocumentResponse` is reused precisely so the raw uploaded bytes and
    the owning `user_id` can't leak through this new endpoint."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-detail-fields@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token)

    response = client.get(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert "content" not in body
    assert "user_id" not in body
    assert set(body) == {"id", "filename", "file_type", "file_size_bytes", "status", "created_at"}


def test_get_another_accounts_document_is_404_not_403(client):
    """Account B must get a 404 for account A's real document id -- a 403
    would confirm the id exists."""
    token_a = _register_and_login(
        client,
        full_name="Account A",
        email="account-a-detail@example.com",
        password="password-account-a",
    )
    token_b = _register_and_login(
        client,
        full_name="Account B",
        email="account-b-detail@example.com",
        password="password-account-b",
    )

    document_a = _upload(client, token_a, filename="account-a-secret.pdf")

    response = client.get(f"/documents/{document_a['id']}", headers=_auth_headers(token_b))

    assert response.status_code == 404
    body = response.json()
    assert body == {"detail": "Document not found."}
    # Nothing about account A's document may appear anywhere in the body.
    assert "account-a-secret" not in response.text

    # ...and account A still reads its own document normally, so the 404 is
    # tenancy, not a broken endpoint.
    response_a = client.get(f"/documents/{document_a['id']}", headers=_auth_headers(token_a))
    assert response_a.status_code == 200
    assert response_a.json()["filename"] == "account-a-secret.pdf"


def test_get_unknown_id_is_the_same_404_as_a_cross_tenant_id(client):
    """An id that exists-but-isn't-yours and an id that doesn't exist at
    all must be indistinguishable to the caller."""
    token_a = _register_and_login(
        client,
        full_name="Account A",
        email="account-a-unknown@example.com",
        password="password-account-a",
    )
    token_b = _register_and_login(
        client,
        full_name="Account B",
        email="account-b-unknown@example.com",
        password="password-account-b",
    )
    document_a = _upload(client, token_a)

    cross_tenant = client.get(f"/documents/{document_a['id']}", headers=_auth_headers(token_b))
    unknown = client.get(f"/documents/{uuid.uuid4()}", headers=_auth_headers(token_b))

    assert unknown.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_get_malformed_id_is_422(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-malformed@example.com",
        password="password12345",
    )

    response = client.get("/documents/not-a-uuid", headers=_auth_headers(token))

    assert response.status_code == 422
    # AD-3: FastAPI's default `{"detail": ...}` envelope, nothing custom.
    assert "detail" in response.json()


def test_get_requires_authentication(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-detail-auth@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token)

    response = client.get(f"/documents/{uploaded['id']}")

    assert response.status_code == 401
