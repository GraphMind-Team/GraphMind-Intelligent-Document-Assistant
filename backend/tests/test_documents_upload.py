"""Upload endpoint tests (Story 2.1): format/size validation, `Uploaded`
status, and that `user_id` is resolved only from the caller's token.
"""


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


def test_upload_valid_pdf_creates_uploaded_row(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", b"%PDF-1.4 fake pdf bytes", "application/pdf")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "report.pdf"
    assert body["file_type"] == "pdf"
    assert body["status"] == "Uploaded"
    assert body["file_size_bytes"] == len(b"%PDF-1.4 fake pdf bytes")
    assert "id" in body
    assert "created_at" in body


def test_upload_markdown_and_html_accepted(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload2@example.com", password="password12345"
    )

    md_response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("notes.md", b"# heading", "text/markdown")},
    )
    html_response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("page.html", b"<html></html>", "text/html")},
    )

    assert md_response.status_code == 201, md_response.text
    assert md_response.json()["file_type"] == "markdown"
    assert html_response.status_code == 201, html_response.text
    assert html_response.json()["file_type"] == "html"


def test_upload_unsupported_format_rejected(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload3@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("resume.docx", b"not really a docx", "application/msword")},
    )

    assert response.status_code == 400
    assert "Supported formats" in response.json()["detail"]


def test_upload_oversized_file_rejected(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload4@example.com", password="password12345"
    )

    oversized = b"a" * (20 * 1024 * 1024 + 1)
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("big.pdf", oversized, "application/pdf")},
    )

    assert response.status_code == 400
    assert "20MB" in response.json()["detail"]


def test_upload_content_type_disagreeing_with_extension_rejected(client):
    # A .pdf extension paired with a content-type outside pdf's allowed
    # set -- the "actively disagrees" case service.py's comment describes,
    # distinct from an unsupported *extension* (already covered above).
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload6@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", b"not a real pdf", "application/msword")},
    )

    assert response.status_code == 400
    assert "Supported formats" in response.json()["detail"]


def test_upload_content_type_with_charset_parameter_accepted(client):
    # Browsers commonly send "text/plain; charset=utf-8" for .md files --
    # must not be rejected just because it isn't a bare "text/plain".
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload7@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("notes.md", b"# heading", "text/plain; charset=utf-8")},
    )

    assert response.status_code == 201, response.text


def test_upload_empty_file_rejected(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload8@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_ignores_client_supplied_user_id_form_field(client):
    # The endpoint takes no user_id field at all -- this pins down that a
    # smuggled one (something a naive future change might start reading)
    # is simply ignored, mirroring test_tenancy.py's /auth/me pattern.
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload9@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        data={"user_id": "00000000-0000-0000-0000-000000000000"},
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 201, response.text


def test_upload_requires_authentication(client):
    response = client.post(
        "/documents",
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_rejected_file_writes_no_row(client, db_session):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-upload5@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("resume.docx", b"not really a docx", "application/msword")},
    )
    assert response.status_code == 400

    from app.shared.models import Document

    assert db_session.query(Document).count() == 0
