"""`GET /documents/{document_id}/content` tests (preview feature).

Reuses `get_document`'s tenancy-scoped lookup, so the load-bearing case
here is the same as `test_documents_detail.py`'s: a cross-tenant or
nonexistent id both 404 identically, and the owner still gets the exact
bytes they uploaded back, media-typed from `file_type`.
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


def _upload(client, token, *, filename, content, content_type):
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_get_content_returns_the_callers_own_bytes_with_correct_media_type(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-content@example.com",
        password="password12345",
    )
    pdf_bytes = b"%PDF-1.4 fake pdf bytes"
    uploaded = _upload(
        client, token, filename="report.pdf", content=pdf_bytes, content_type="application/pdf"
    )

    response = client.get(f"/documents/{uploaded['id']}/content", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == pdf_bytes


def test_get_content_media_type_matches_markdown_and_html(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-content-types@example.com",
        password="password12345",
    )
    md_bytes = b"# Title\n\nSome body text."
    html_bytes = b"<html><body>Hi</body></html>"

    md_doc = _upload(
        client, token, filename="notes.md", content=md_bytes, content_type="text/markdown"
    )
    html_doc = _upload(
        client, token, filename="page.html", content=html_bytes, content_type="text/html"
    )

    md_response = client.get(f"/documents/{md_doc['id']}/content", headers=_auth_headers(token))
    html_response = client.get(
        f"/documents/{html_doc['id']}/content", headers=_auth_headers(token)
    )

    assert md_response.status_code == 200
    assert md_response.headers["content-type"].startswith("text/markdown")
    assert md_response.content == md_bytes

    assert html_response.status_code == 200
    assert html_response.headers["content-type"].startswith("text/html")
    assert html_response.content == html_bytes


def test_get_content_another_accounts_document_is_404_not_403(client):
    token_a = _register_and_login(
        client,
        full_name="Account A",
        email="account-a-content@example.com",
        password="password-account-a",
    )
    token_b = _register_and_login(
        client,
        full_name="Account B",
        email="account-b-content@example.com",
        password="password-account-b",
    )

    document_a = _upload(
        client,
        token_a,
        filename="account-a-secret.pdf",
        content=b"%PDF-1.4 secret bytes",
        content_type="application/pdf",
    )

    response = client.get(f"/documents/{document_a['id']}/content", headers=_auth_headers(token_b))

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}
    assert b"secret bytes" not in response.content


def test_get_content_unknown_id_is_the_same_404_as_a_cross_tenant_id(client):
    token_a = _register_and_login(
        client,
        full_name="Account A",
        email="account-a-content-unknown@example.com",
        password="password-account-a",
    )
    token_b = _register_and_login(
        client,
        full_name="Account B",
        email="account-b-content-unknown@example.com",
        password="password-account-b",
    )
    document_a = _upload(
        client,
        token_a,
        filename="report.pdf",
        content=b"%PDF-1.4 fake pdf bytes",
        content_type="application/pdf",
    )

    cross_tenant = client.get(
        f"/documents/{document_a['id']}/content", headers=_auth_headers(token_b)
    )
    unknown = client.get(f"/documents/{uuid.uuid4()}/content", headers=_auth_headers(token_b))

    assert unknown.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_get_content_is_nosniff_and_uncached(client):
    """The two headers that make serving user-uploaded bytes inline safe.

    `nosniff` stops a browser from sniffing past the declared media type and
    deciding an uploaded document is HTML worth executing; `no-store` keeps
    per-tenant bytes out of shared caches and off disk. Neither is load
    bearing while auth is Bearer-only (a direct navigation 401s first) --
    they are what keeps this route safe if auth ever moves to a cookie.
    """
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-content-headers@example.com",
        password="password12345",
    )
    uploaded = _upload(
        client,
        token,
        filename="page.html",
        content=b"<html><body><script>alert(1)</script></body></html>",
        content_type="text/html",
    )

    response = client.get(f"/documents/{uploaded['id']}/content", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"


def test_get_content_disposition_encodes_a_hostile_filename(client):
    """A filename is client-supplied input, not a trusted string.

    Interpolated raw into `Content-Disposition` it would let a CR/LF split
    the header, and would mangle any non-ASCII name besides -- so the
    filename goes out RFC 5987 percent-encoded, never verbatim.
    """
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-content-filename@example.com",
        password="password12345",
    )
    uploaded = _upload(
        client,
        token,
        filename='отчёт "final".pdf',
        content=b"%PDF-1.4 fake pdf bytes",
        content_type="application/pdf",
    )

    response = client.get(f"/documents/{uploaded['id']}/content", headers=_auth_headers(token))

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("inline; filename*=UTF-8''")
    # Percent-encoded, so neither the quote nor any non-ASCII byte reaches
    # the header verbatim.
    assert '"' not in disposition
    assert disposition.isascii()
    assert "%D0%BE%D1%82%D1%87" in disposition


def test_get_content_requires_authentication(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-content-auth@example.com",
        password="password12345",
    )
    uploaded = _upload(
        client,
        token,
        filename="report.pdf",
        content=b"%PDF-1.4 fake pdf bytes",
        content_type="application/pdf",
    )

    response = client.get(f"/documents/{uploaded['id']}/content")

    assert response.status_code == 401
