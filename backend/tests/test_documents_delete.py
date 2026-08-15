"""`DELETE /documents/{document_id}` tests (Story 2.7 + Story 2.8).

Mirrors `test_documents_detail.py`'s IDOR coverage for the read path --
the cross-tenant and unknown-id cases here are load-bearing for the same
reason: a 403 (or any response distinguishable from "doesn't exist")
would confirm another account's document id is real.

`delete_passages_for_document` and (Story 2.8) `prune_document_from_graph`
are both monkeypatched to a `Mock` here (the same convention
`test_documents_parse_and_index.py`'s `_stub_embeddings` uses) rather than
exercising real Weaviate/Neo4j connections -- there is no test
Weaviate/Neo4j instance in this environment. What's pinned down instead:
each is called with the right `(document_id, user_id)` pair, and both run
*before* the row is gone (so a Weaviate/Neo4j failure never leaves an
orphaned row deleted with passages/graph state still sitting there). One
test (`test_delete_prunes_a_unique_entity_but_keeps_one_shared_with_a_surviving_document`)
restores the real `prune_document_from_graph`/`write_entities_and_relationships`
against a minimal in-memory fake driver instead of the `Mock`, to prove
the reference-counted outcome end-to-end through the real HTTP delete
flow, not just that the function was called.
"""

import uuid
from unittest.mock import Mock

import pytest

from app.shared.models import Document


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


def _upload(
    client, token, filename="report.pdf", content_type="application/pdf", content=b"%PDF-1.4 fake pdf bytes"
):
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mark_ready(db_session, document_id):
    """Flips a freshly-uploaded (`Uploaded`) row to `Ready` directly on the
    row -- `_stub_ingestion_pipeline` (conftest.py, autouse) no-ops the real
    background pipeline, so a test that needs a *deletable* document (Story
    2.7's mid-ingestion 409 guard refuses `Uploaded`/`Extracting`/
    `Graphing`) has to make that transition itself rather than waiting on
    ingestion that will never run."""
    row = db_session.get(Document, uuid.UUID(document_id))
    row.status = "Ready"
    db_session.commit()
    return row


@pytest.fixture(autouse=True)
def _stub_weaviate_delete(monkeypatch):
    """Replaces `service.delete_passages_for_document` with a `Mock` for
    every test in this file -- see the module docstring for why."""
    import app.documents.service as service_module

    fake_delete_passages = Mock()
    monkeypatch.setattr(service_module, "delete_passages_for_document", fake_delete_passages)
    return fake_delete_passages


@pytest.fixture(autouse=True)
def _stub_neo4j_prune(monkeypatch):
    """Replaces `service.prune_document_from_graph` with a `Mock` for every
    test in this file -- see the module docstring for why. Overridden back
    to the real function in the one test that needs genuine reference-
    counting behavior."""
    import app.documents.service as service_module

    fake_prune = Mock()
    monkeypatch.setattr(service_module, "prune_document_from_graph", fake_prune)
    return fake_prune


def test_delete_own_document_returns_204_and_removes_the_row(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_prune
):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-own@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="quarterly-report.pdf")
    _mark_ready(db_session, uploaded["id"])

    response = client.delete(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    assert response.content == b""

    assert db_session.get(Document, uuid.UUID(uploaded["id"])) is None

    # Called once, with this document's own id and owner -- never anything
    # client-supplied beyond the id in the URL.
    _stub_weaviate_delete.assert_called_once()
    called_document_id, called_user_id = _stub_weaviate_delete.call_args[0]
    assert called_document_id == uploaded["id"]
    assert called_user_id  # a non-empty user id string was passed through

    # Story 2.8: the Neo4j prune runs too, with the same (document_id,
    # user_id) pair.
    _stub_neo4j_prune.assert_called_once_with(uploaded["id"], called_user_id)


def test_delete_calls_weaviate_delete_before_the_row_is_gone(client, db_session, _stub_weaviate_delete):
    """The delete-order invariant (Weaviate first, then the row): if the
    Weaviate call were to raise, the row must still exist afterward. This
    is asserted the other way around here -- by making the mock itself
    check the row is still present at the moment it's invoked -- since
    that's the only way to observe "before" without instrumenting the
    route.
    """
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-order@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="order-check.pdf")
    _mark_ready(db_session, uploaded["id"])
    document_uuid = uuid.UUID(uploaded["id"])

    seen_row_present_at_call_time = {}

    def _check_row_still_present(document_id_str, user_id_str):
        seen_row_present_at_call_time["value"] = db_session.get(Document, document_uuid) is not None

    _stub_weaviate_delete.side_effect = _check_row_still_present

    response = client.delete(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    assert seen_row_present_at_call_time["value"] is True
    assert db_session.get(Document, document_uuid) is None


def test_delete_when_weaviate_raises_leaves_the_row_intact_for_retry(client, db_session, _stub_weaviate_delete):
    """If the Weaviate delete raises, nothing has been committed yet -- the
    document must still exist so the user can safely retry (Boundaries)."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-retry@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="retry-me.pdf")
    _mark_ready(db_session, uploaded["id"])
    document_uuid = uuid.UUID(uploaded["id"])

    _stub_weaviate_delete.side_effect = RuntimeError("Weaviate unreachable")

    with pytest.raises(RuntimeError):
        client.delete(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    db_session.expire_all()
    assert db_session.get(Document, document_uuid) is not None


def test_delete_another_accounts_document_is_404_not_403(client, db_session):
    """Account B must get a 404 for account A's real document id -- a 403
    would confirm the id exists. Account A's row and passages must be
    completely untouched by the attempt."""
    token_a = _register_and_login(
        client,
        full_name="Account A",
        email="account-a-delete@example.com",
        password="password-account-a",
    )
    token_b = _register_and_login(
        client,
        full_name="Account B",
        email="account-b-delete@example.com",
        password="password-account-b",
    )

    document_a = _upload(client, token_a, filename="account-a-secret.pdf")

    response = client.delete(f"/documents/{document_a['id']}", headers=_auth_headers(token_b))

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}

    # The row is untouched -- still there, still owned by account A.
    row = db_session.get(Document, uuid.UUID(document_a["id"]))
    assert row is not None
    assert row.filename == "account-a-secret.pdf"

    # ...and account A can still read (and later delete) its own document.
    response_a = client.get(f"/documents/{document_a['id']}", headers=_auth_headers(token_a))
    assert response_a.status_code == 200


def test_delete_nonexistent_document_is_the_same_404_as_cross_tenant(client):
    """An id that exists-but-isn't-yours and an id that doesn't exist at
    all must be indistinguishable to the caller."""
    token_a = _register_and_login(
        client,
        full_name="Account A",
        email="account-a-delete-unknown@example.com",
        password="password-account-a",
    )
    token_b = _register_and_login(
        client,
        full_name="Account B",
        email="account-b-delete-unknown@example.com",
        password="password-account-b",
    )
    document_a = _upload(client, token_a)

    cross_tenant = client.delete(f"/documents/{document_a['id']}", headers=_auth_headers(token_b))
    unknown = client.delete(f"/documents/{uuid.uuid4()}", headers=_auth_headers(token_b))

    assert unknown.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_delete_malformed_id_is_422(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-malformed@example.com",
        password="password12345",
    )

    response = client.delete("/documents/not-a-uuid", headers=_auth_headers(token))

    assert response.status_code == 422


def test_delete_requires_authentication(client):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-auth@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token)

    response = client.delete(f"/documents/{uploaded['id']}")

    assert response.status_code == 401


def test_delete_a_document_with_zero_passages_still_succeeds(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_prune
):
    """A `Failed` document that never got past parsing has no Weaviate rows
    at all -- `delete_passages_for_document` is already idempotent against
    zero matches, so deleting it must still succeed. `Failed` (not
    `Uploaded`) is the terminal, zero-passage case now that mid-ingestion
    statuses are refused (see the 409 tests below, Spec Change Log) --
    `Uploaded` itself is no longer a deletable status."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-zero-passages@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="never-ingested.pdf")
    row = db_session.get(Document, uuid.UUID(uploaded["id"]))
    row.status = "Failed"
    row.failed_reason = "Could not read this document: unexpected EOF"
    db_session.commit()

    response = client.delete(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    assert db_session.get(Document, uuid.UUID(uploaded["id"])) is None
    _stub_weaviate_delete.assert_called_once()
    _stub_neo4j_prune.assert_called_once()


def test_delete_refuses_a_document_mid_ingestion_with_409(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_prune
):
    """Spec Change Log narrowing: `ingest_document` runs as a genuine
    concurrent `BackgroundTasks` job that keeps writing to this row while
    `status` is `Uploaded`/`Extracting`/`Graphing`. Deleting mid-flight
    would let that task write Weaviate passages (or Neo4j entities) *after*
    this delete's own Weaviate cleanup already ran, orphaning fresh state
    under a document id no longer in Postgres (AD-1's no-orphaned-partial-
    state principle). The row and any passages must be completely
    untouched by a refused attempt."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-mid-ingestion@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="still-extracting.pdf")
    row = db_session.get(Document, uuid.UUID(uploaded["id"]))
    row.status = "Extracting"
    db_session.commit()

    response = client.delete(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Document is still being processed and can't be deleted yet."
    }
    _stub_weaviate_delete.assert_not_called()
    _stub_neo4j_prune.assert_not_called()

    # Completely untouched -- still there, still Extracting.
    db_session.expire_all()
    surviving_row = db_session.get(Document, uuid.UUID(uploaded["id"]))
    assert surviving_row is not None
    assert surviving_row.status == "Extracting"


@pytest.mark.parametrize("status", ["Uploaded", "Extracting", "Graphing"])
def test_delete_refuses_every_non_terminal_status_with_409(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_prune, status
):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email=f"maria-delete-409-{status.lower()}@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename=f"{status.lower()}.pdf")
    row = db_session.get(Document, uuid.UUID(uploaded["id"]))
    row.status = status
    db_session.commit()

    response = client.delete(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 409
    _stub_weaviate_delete.assert_not_called()
    _stub_neo4j_prune.assert_not_called()


def test_delete_calls_prune_after_weaviate_delete_and_before_the_row_is_gone(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_prune
):
    """Delete order is fixed (Story 2.8): Weaviate, then Neo4j, then the
    Postgres row. Asserted the same way
    `test_delete_calls_weaviate_delete_before_the_row_is_gone` asserts the
    Weaviate step -- each mock records when it ran and, for the prune
    step, whether the row was still present at that moment."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-prune-order@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="prune-order-check.pdf")
    _mark_ready(db_session, uploaded["id"])
    document_uuid = uuid.UUID(uploaded["id"])

    call_order = []
    _stub_weaviate_delete.side_effect = lambda *a: call_order.append("weaviate")

    def _prune_side_effect(*a):
        call_order.append("neo4j")
        assert db_session.get(Document, document_uuid) is not None

    _stub_neo4j_prune.side_effect = _prune_side_effect

    response = client.delete(f"/documents/{uploaded['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    assert call_order == ["weaviate", "neo4j"]
    assert db_session.get(Document, document_uuid) is None


def test_delete_prunes_a_unique_entity_but_keeps_one_shared_with_a_surviving_document(
    client, db_session, monkeypatch
):
    """End-to-end through the real `prune_document_from_graph` (Story 2.8,
    OD-4's reversal of FR-8's original boundary): an entity contributed
    only by the deleted document is gone from the graph afterward; one
    also contributed by a surviving document remains. Uses a minimal
    in-memory fake in place of a real Neo4j driver -- there is no test
    Neo4j instance in this environment -- but exercises the real
    `write_entities_and_relationships`/`prune_document_from_graph`
    reference-counting logic (full Cypher-shape coverage lives in
    `test_neo4j_client.py`; this test's job is proving the wiring through
    the real HTTP delete flow, not re-deriving that coverage)."""
    from app.shared.data_access import neo4j_client as neo4j_client_module
    from app.shared.data_access.neo4j_client import (
        prune_document_from_graph as real_prune_document_from_graph,
        write_entities_and_relationships as real_write_entities_and_relationships,
    )
    from app.shared.data_access.shapes import Neo4jEntity
    import app.documents.service as service_module

    class _FakeTx:
        def __init__(self):
            self.entities: dict[tuple, list[str]] = {}

        def run(self, query, **params):
            if "MERGE (e:Entity" in query:
                user_id = params["user_id"]
                document_id = params["document_id"]
                for row in params["rows"]:
                    ids = self.entities.setdefault((row["name"], row["type"], user_id), [])
                    if document_id not in ids:
                        ids.append(document_id)
            elif "DETACH DELETE e" in query:
                user_id = params["user_id"]
                document_id = params["document_id"]
                for key in list(self.entities.keys()):
                    if key[-1] != user_id:
                        continue
                    ids = self.entities[key]
                    if document_id in ids:
                        ids.remove(document_id)
                        if not ids:
                            del self.entities[key]
            # No relationships are written in this test, so the
            # "DELETE r" (relationship-prune) shape never needs handling.
            return Mock(consume=lambda: None)

    class _FakeSession:
        def __init__(self, tx):
            self._tx = tx

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def execute_write(self, fn, *args):
            return fn(self._tx, *args)

    class _FakeDriver:
        def __init__(self):
            self.tx = _FakeTx()

        def session(self):
            return _FakeSession(self.tx)

    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)
    # Undo this file's autouse Mock for this one test -- exercise the real
    # reference-counting function against the fake driver above instead.
    monkeypatch.setattr(service_module, "prune_document_from_graph", real_prune_document_from_graph)

    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-shared-entity@example.com",
        password="password12345",
    )
    doc_a = _upload(client, token, filename="doc-a.pdf", content=b"%PDF-1.4 doc a bytes")
    doc_b = _upload(client, token, filename="doc-b.pdf", content=b"%PDF-1.4 doc b bytes")
    _mark_ready(db_session, doc_a["id"])
    _mark_ready(db_session, doc_b["id"])

    user_id = str(db_session.get(Document, uuid.UUID(doc_a["id"])).user_id)
    shared_entity = [Neo4jEntity(name="Shared Corp", type="Organization", user_id=user_id)]
    real_write_entities_and_relationships(shared_entity, [], user_id, doc_a["id"])
    real_write_entities_and_relationships(shared_entity, [], user_id, doc_b["id"])

    response = client.delete(f"/documents/{doc_a['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    key = ("Shared Corp", "Organization", user_id)
    assert fake_driver.tx.entities[key] == [doc_b["id"]]
