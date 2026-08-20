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


def test_upload_rate_limit_returns_429_past_the_window_budget(client, _fresh_rate_limiters):
    _, _, _, _, upload_rate_limiter, _ = _fresh_rate_limiters
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-ratelimit@example.com", password="password12345"
    )

    # 30/minute is the configured budget -- the 31st within the window is
    # the first that must be refused. Content varies per iteration
    # (Story 2.6) -- otherwise every upload after the first would hit the
    # content-hash dedupe path and never reach a fresh 201, which isn't
    # what this test is pinning down.
    for i in range(upload_rate_limiter._max_attempts):
        ok = client.post(
            "/documents",
            headers=_auth_headers(token),
            files={"file": ("notes.md", f"# heading {i}".encode(), "text/markdown")},
        )
        assert ok.status_code == 201, ok.text

    refused = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("notes.md", b"# heading, past the budget", "text/markdown")},
    )
    assert refused.status_code == 429
    assert "Too many uploads" in refused.json()["detail"]


def test_upload_rate_limit_is_per_account(client):
    # Account A exhausting its budget must not refuse account B.
    token_a = _register_and_login(
        client, full_name="Account A", email="maria-ratelimit-a@example.com", password="password12345"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="maria-ratelimit-b@example.com", password="password12345"
    )

    for _ in range(30):
        client.post(
            "/documents",
            headers=_auth_headers(token_a),
            files={"file": ("notes.md", b"# heading", "text/markdown")},
        )

    assert (
        client.post(
            "/documents",
            headers=_auth_headers(token_a),
            files={"file": ("notes.md", b"# heading", "text/markdown")},
        ).status_code
        == 429
    )
    b_response = client.post(
        "/documents",
        headers=_auth_headers(token_b),
        files={"file": ("notes.md", b"# heading", "text/markdown")},
    )
    assert b_response.status_code == 201, b_response.text


def test_upload_concurrency_limiter_rejects_past_max_in_flight(_fresh_rate_limiters):
    # The concurrency limiter is exercised directly rather than through the
    # TestClient: TestClient issues requests synchronously, so no two
    # uploads are ever genuinely in flight at once through it.
    import pytest as _pytest
    from fastapi import HTTPException

    _, _, _, _, _, limiter = _fresh_rate_limiters
    user_key = "some-user-id"

    with limiter.slot(user_key), limiter.slot(user_key), limiter.slot(user_key), limiter.slot(
        user_key
    ), limiter.slot(user_key):
        # 5 slots held (the configured max) -- the 6th must be refused.
        with _pytest.raises(HTTPException) as excinfo:
            with limiter.slot(user_key):
                pass
        assert excinfo.value.status_code == 429

    # All slots released on context exit -- a fresh one is admitted again,
    # and the key is dropped rather than left at 0.
    with limiter.slot(user_key):
        pass
    assert user_key not in limiter._in_flight


def test_upload_concurrency_limiter_releases_slot_on_exception(_fresh_rate_limiters):
    _, _, _, _, _, limiter = _fresh_rate_limiters
    user_key = "erroring-user"

    try:
        with limiter.slot(user_key):
            raise ValueError("upload blew up mid-request")
    except ValueError:
        pass

    # A slot leaked here would permanently shrink the user's budget.
    assert user_key not in limiter._in_flight


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


def test_upload_first_time_sets_is_duplicate_false(client):
    # Story 2.6: unchanged-behavior side of the new field -- new row, 201,
    # `is_duplicate: false`.
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-dedupe1@example.com", password="password12345"
    )

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", b"%PDF-1.4 identical bytes", "application/pdf")},
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_duplicate"] is False


def test_upload_byte_identical_reupload_same_filename_is_duplicate(client, db_session):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-dedupe2@example.com", password="password12345"
    )
    content = b"%PDF-1.4 identical bytes for dedupe"

    first = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    second = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["is_duplicate"] is True
    assert body["id"] == first_id

    from app.shared.models import Document

    assert db_session.query(Document).count() == 1


def test_upload_byte_identical_reupload_different_filename_is_duplicate(client, db_session):
    # Matched on hash only -- filename ignored (AC3).
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-dedupe3@example.com", password="password12345"
    )
    content = b"%PDF-1.4 identical bytes, renamed on re-upload"

    first = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("original.pdf", content, "application/pdf")},
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    second = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("renamed.pdf", content, "application/pdf")},
    )

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["is_duplicate"] is True
    assert body["id"] == first_id
    # Filename ignored -- the returned body is the *existing* document.
    assert body["filename"] == "original.pdf"

    from app.shared.models import Document

    assert db_session.query(Document).count() == 1


def test_upload_edited_content_reuploaded_under_original_filename_is_not_duplicate(client, db_session):
    # AC4: content differs (even under the identical filename) -> genuinely
    # new document, ingested as usual.
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-dedupe4@example.com", password="password12345"
    )

    first = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", b"%PDF-1.4 original content", "application/pdf")},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", b"%PDF-1.4 edited content", "application/pdf")},
    )

    assert second.status_code == 201, second.text
    body = second.json()
    assert body["is_duplicate"] is False
    assert body["id"] != first.json()["id"]

    from app.shared.models import Document

    assert db_session.query(Document).count() == 2


def test_upload_does_not_schedule_ingestion_on_duplicate(client, _stub_ingestion_pipeline):
    # NFR-7: no parse/embed/LLM call for a duplicate -- pinned down here by
    # asserting the background-task stub was invoked exactly once (for the
    # first, genuinely-new upload) and never again for the duplicate.
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-dedupe5@example.com", password="password12345"
    )
    content = b"%PDF-1.4 no ingestion on duplicate"

    client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )
    assert _stub_ingestion_pipeline.call_count == 1

    client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )
    assert _stub_ingestion_pipeline.call_count == 1


def test_upload_content_hash_dedupe_scoped_per_user(client):
    # AD-2 / spec's "Never: no dedupe across users" -- the same bytes from
    # two different accounts must each create their own row.
    token_a = _register_and_login(
        client, full_name="Account A", email="maria-dedupe6a@example.com", password="password12345"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="maria-dedupe6b@example.com", password="password12345"
    )
    content = b"%PDF-1.4 shared bytes across two accounts"

    response_a = client.post(
        "/documents",
        headers=_auth_headers(token_a),
        files={"file": ("report.pdf", content, "application/pdf")},
    )
    response_b = client.post(
        "/documents",
        headers=_auth_headers(token_b),
        files={"file": ("report.pdf", content, "application/pdf")},
    )

    assert response_a.status_code == 201, response_a.text
    assert response_b.status_code == 201, response_b.text
    assert response_a.json()["is_duplicate"] is False
    assert response_b.json()["is_duplicate"] is False
    assert response_a.json()["id"] != response_b.json()["id"]


def test_upload_concurrent_duplicate_race_resolves_to_one_row_never_500s(db_session, monkeypatch):
    # Simulates the race the DB unique constraint exists to close: two
    # requests both miss the pre-create hash lookup and both reach
    # `service.upload_document`'s insert. The first genuinely creates the
    # row; for the second, `get_document_by_content_hash` is patched to
    # return `None` on its *first* call only (reproducing "missed the
    # pre-create lookup because the first request hadn't committed yet"),
    # so the second call proceeds to `INSERT`, hits the composite unique
    # index, and `service.upload_document`'s own `except IntegrityError`
    # branch must roll back, re-query (unpatched, for real this time), and
    # return the first row as a duplicate -- not raise, not 500.
    import uuid as uuid_module

    from app.auth.repository import create_user
    from app.auth.service import hash_password
    from app.documents import repository, service
    from app.shared.models import Document, User

    user = create_user(
        db_session,
        User(
            id=uuid_module.uuid4(),
            full_name="Race Tester",
            email="maria-dedupe-race@example.com",
            password_hash=hash_password("password12345"),
        ),
    )
    db_session.commit()

    content = b"%PDF-1.4 racing concurrent uploads"

    document_1, outcome_1 = service.upload_document(
        db_session, user, filename="a.pdf", file_type="pdf", content=content
    )
    assert outcome_1 == "created"

    real_lookup = repository.get_document_by_content_hash
    calls = {"count": 0}

    def _lookup_missing_once(db, user_id, content_hash):
        calls["count"] += 1
        if calls["count"] == 1:
            return None  # the race: pre-create lookup misses the not-yet-committed row
        return real_lookup(db, user_id, content_hash)

    monkeypatch.setattr(repository, "get_document_by_content_hash", _lookup_missing_once)

    document_2, outcome_2 = service.upload_document(
        db_session, user, filename="b.pdf", file_type="pdf", content=content
    )

    assert outcome_2 == "duplicate"
    assert document_2.id == document_1.id
    assert db_session.query(Document).count() == 1


def test_upload_byte_identical_reupload_of_a_failed_document_reingests_in_place(
    client, db_session, _stub_ingestion_pipeline
):
    # A real bug found by independent review after this story's first
    # merge: re-uploading a Failed document's exact bytes used to be
    # swallowed as a plain duplicate, silently removing the only recovery
    # path a user had (no retry endpoint exists anywhere in this
    # codebase). Fixed: a hash match against a Failed document is reset to
    # Uploaded and retried in place -- no second row, but ingestion *is*
    # scheduled, same as a fresh upload.
    from app.shared.models import Document

    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-reingest1@example.com", password="password12345"
    )
    content = b"%PDF-1.4 was failed, reuploaded identical"

    first = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )
    assert first.status_code == 201, first.text
    document_id = first.json()["id"]

    import uuid as uuid_module

    row = db_session.get(Document, uuid_module.UUID(document_id))
    row.status = "Failed"
    row.failed_reason = "Could not read this document: unexpected EOF"
    db_session.commit()

    _stub_ingestion_pipeline.reset_mock()

    second = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["id"] == document_id
    assert body["status"] == "Uploaded"
    assert body["is_duplicate"] is False
    assert body["failed_reason"] is None

    assert _stub_ingestion_pipeline.call_count == 1
    assert db_session.query(Document).count() == 1


def test_upload_byte_identical_reupload_of_a_ready_document_does_not_reingest(
    client, _stub_ingestion_pipeline
):
    # The counterpart to the reingest test above: a hash match against a
    # non-Failed document (Ready, Uploaded, Extracting, Graphing) is still
    # a plain duplicate -- reingest-in-place is specific to Failed.
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-reingest2@example.com", password="password12345"
    )
    content = b"%PDF-1.4 was never failed"

    first = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )
    assert first.status_code == 201, first.text
    assert _stub_ingestion_pipeline.call_count == 1

    second = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", content, "application/pdf")},
    )

    assert second.status_code == 200, second.text
    assert second.json()["is_duplicate"] is True
    # Still only the first upload's ingestion call -- unchanged from the
    # already-covered duplicate path.
    assert _stub_ingestion_pipeline.call_count == 1


def test_claim_failed_document_for_reingest_loses_race_falls_back_to_duplicate(
    db_session, monkeypatch
):
    # Mirrors the concurrent-create race test above, but for the
    # concurrent-reingest race: two identical re-uploads of the same
    # Failed document both see status == "Failed" before either claims it.
    # `claim_failed_document_for_reingest` is the atomic guard -- simulated
    # here by forcing it to report a lost claim (as it genuinely would if a
    # concurrent request's UPDATE landed first), and asserting the loser
    # falls back to "duplicate" rather than scheduling a second pipeline
    # against a row someone else is already reprocessing.
    import uuid as uuid_module

    from app.auth.repository import create_user
    from app.auth.service import hash_password
    from app.documents import repository, service
    from app.shared.models import Document, User

    user = create_user(
        db_session,
        User(
            id=uuid_module.uuid4(),
            full_name="Race Tester",
            email="maria-reingest-race@example.com",
            password_hash=hash_password("password12345"),
        ),
    )
    db_session.commit()

    content = b"%PDF-1.4 racing reingest of a failed document"
    document, outcome = service.upload_document(
        db_session, user, filename="a.pdf", file_type="pdf", content=content
    )
    assert outcome == "created"
    document.status = "Failed"
    document.failed_reason = "Could not read this document: boom"
    db_session.commit()

    monkeypatch.setattr(repository, "claim_failed_document_for_reingest", lambda db, doc_id: False)

    document_2, outcome_2 = service.upload_document(
        db_session, user, filename="b.pdf", file_type="pdf", content=content
    )

    assert outcome_2 == "duplicate"
    assert document_2.id == document.id
    assert db_session.query(Document).count() == 1
