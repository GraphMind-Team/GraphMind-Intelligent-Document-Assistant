"""`PATCH /documents/{document_id}` tests (folder-grouping feature).

Covers the document-side of folder assignment: happy path, unassign, a
cross-tenant `folder_id`, and the same 404-not-403 IDOR convention every
other by-id document endpoint in this codebase already follows (see
`test_documents_detail.py`/`test_documents_delete.py`).
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


def _create_folder(client, token, name="Contracts", color="mint"):
    response = client.post(
        "/folders", headers=_auth_headers(token), json={"name": name, "color": color}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_assign_document_to_own_folder_returns_200_with_the_folder_id(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="assign-happy@example.com", password="password12345"
    )
    uploaded = _upload(client, token)
    folder = _create_folder(client, token)

    response = client.patch(
        f"/documents/{uploaded['id']}",
        headers=_auth_headers(token),
        json={"folder_id": folder["id"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == uploaded["id"]
    assert body["folder_id"] == folder["id"]

    # Persisted -- a subsequent GET reflects it too.
    get_response = client.get(f"/documents/{uploaded['id']}", headers=_auth_headers(token))
    assert get_response.json()["folder_id"] == folder["id"]


def test_unassign_document_sets_folder_id_to_null(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="assign-unassign@example.com", password="password12345"
    )
    uploaded = _upload(client, token)
    folder = _create_folder(client, token)
    client.patch(
        f"/documents/{uploaded['id']}", headers=_auth_headers(token), json={"folder_id": folder["id"]}
    )

    response = client.patch(
        f"/documents/{uploaded['id']}", headers=_auth_headers(token), json={"folder_id": None}
    )

    assert response.status_code == 200, response.text
    assert response.json()["folder_id"] is None


def test_assign_to_another_users_folder_is_404_folder_not_found(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="assign-cross-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="assign-cross-b@example.com", password="password-account-b"
    )
    document_b = _upload(client, token_b, filename="b-doc.pdf")
    folder_a = _create_folder(client, token_a, name="Account A Folder")

    response = client.patch(
        f"/documents/{document_b['id']}",
        headers=_auth_headers(token_b),
        json={"folder_id": folder_a["id"]},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Folder not found."}

    # The document itself is untouched -- still unfiled.
    get_response = client.get(f"/documents/{document_b['id']}", headers=_auth_headers(token_b))
    assert get_response.json()["folder_id"] is None


def test_assign_nonexistent_folder_id_is_404_folder_not_found(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="assign-unknown-folder@example.com", password="password12345"
    )
    uploaded = _upload(client, token)

    response = client.patch(
        f"/documents/{uploaded['id']}",
        headers=_auth_headers(token),
        json={"folder_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Folder not found."}


def test_assign_folder_to_another_accounts_document_is_404_document_not_found(client):
    """The document-ownership check runs first: account B can't even reach
    the folder-ownership check by targeting account A's document id."""
    token_a = _register_and_login(
        client, full_name="Account A", email="assign-doc-cross-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="assign-doc-cross-b@example.com", password="password-account-b"
    )
    document_a = _upload(client, token_a, filename="a-secret.pdf")
    folder_b = _create_folder(client, token_b)

    response = client.patch(
        f"/documents/{document_a['id']}",
        headers=_auth_headers(token_b),
        json={"folder_id": folder_b["id"]},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_assign_nonexistent_document_id_is_404(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="assign-unknown-doc@example.com", password="password12345"
    )

    response = client.patch(
        f"/documents/{uuid.uuid4()}", headers=_auth_headers(token), json={"folder_id": None}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_assign_requires_authentication(client):
    response = client.patch(f"/documents/{uuid.uuid4()}", json={"folder_id": None})
    assert response.status_code == 401


def test_assign_malformed_document_id_is_422(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="assign-malformed@example.com", password="password12345"
    )

    response = client.patch(
        "/documents/not-a-uuid", headers=_auth_headers(token), json={"folder_id": None}
    )

    assert response.status_code == 422


def test_reassign_document_from_one_folder_to_another(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="assign-reassign@example.com", password="password12345"
    )
    uploaded = _upload(client, token)
    folder_1 = _create_folder(client, token, name="First", color="mint")
    folder_2 = _create_folder(client, token, name="Second", color="sky")

    client.patch(
        f"/documents/{uploaded['id']}", headers=_auth_headers(token), json={"folder_id": folder_1["id"]}
    )
    response = client.patch(
        f"/documents/{uploaded['id']}", headers=_auth_headers(token), json={"folder_id": folder_2["id"]}
    )

    assert response.status_code == 200, response.text
    assert response.json()["folder_id"] == folder_2["id"]
