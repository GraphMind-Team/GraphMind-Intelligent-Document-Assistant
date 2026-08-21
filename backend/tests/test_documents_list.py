"""List endpoint tests (Story 2.1): minimal proof a row appears
post-upload, and cross-tenant isolation (re-verifies SM-3 against real
documents, per the story's I/O matrix)."""


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


def test_list_returns_uploaded_document(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-list@example.com", password="password12345"
    )
    uploaded = _upload(client, token)

    response = client.get("/documents", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == uploaded["id"]
    assert body[0]["status"] == "Uploaded"
    # Folder-grouping feature: `GET /documents` is the primary consumer of
    # `folder_id` (`DocumentsPage.jsx` calls list, not the by-id detail
    # endpoint) -- a freshly uploaded, never-assigned document must come
    # back Unfiled (`None`), not the field being silently absent.
    assert "folder_id" in body[0]
    assert body[0]["folder_id"] is None


def test_list_requires_authentication(client):
    response = client.get("/documents")
    assert response.status_code == 401


def test_list_is_scoped_to_the_calling_account(client):
    """Account B must never see account A's uploaded documents."""
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a-docs@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b-docs@example.com", password="password-account-b"
    )

    _upload(client, token_a, filename="account-a-file.pdf")

    response_b = client.get("/documents", headers=_auth_headers(token_b))

    assert response_b.status_code == 200
    assert response_b.json() == []

    response_a = client.get("/documents", headers=_auth_headers(token_a))
    assert response_a.status_code == 200
    assert len(response_a.json()) == 1
    assert response_a.json()[0]["filename"] == "account-a-file.pdf"
