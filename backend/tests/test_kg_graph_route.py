"""`GET /kg/graph` route tests (Story 4.1): the happy-path response shape,
auth requirement, and -- the highest-stakes guarantee this story makes --
that the route always resolves `user_id` server-side from the JWT-derived
account, never from anything the client could influence.

The Neo4j call itself is mocked at its call-site-bound name in
`app.kg.service` (mirrors `test_chat_ask_route.py`'s convention of
patching at the importing module, not the definition module) -- there's
no live Neo4j in CI, the same accepted gap `test_neo4j_client.py` already
documents for the write path.
"""

from unittest.mock import MagicMock

from app.kg import service as kg_service_module


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


def test_get_graph_returns_the_expected_shape(client, monkeypatch):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-graph@example.com", password="password12345"
    )
    fake_get_graph_for_user = MagicMock(
        return_value=(
            [{"name": "Maria Ivanova", "type": "Person", "degree": 1}],
            [
                {
                    "source_name": "Maria Ivanova",
                    "source_type": "Person",
                    "target_name": "TechCorp",
                    "target_type": "Organization",
                    "relationship_type": "WORKS_AT",
                }
            ],
            1,
        )
    )
    monkeypatch.setattr(kg_service_module, "get_graph_for_user", fake_get_graph_for_user)

    response = client.get("/kg/graph", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["nodes"] == [{"id": "Person:Maria Ivanova", "name": "Maria Ivanova", "type": "Person", "degree": 1}]
    assert body["edges"] == [
        {"source": "Person:Maria Ivanova", "target": "Organization:TechCorp", "type": "WORKS_AT"}
    ]
    assert body["total_node_count"] == 1


def test_get_graph_with_no_entities_returns_empty_arrays(client, monkeypatch):
    token = _register_and_login(
        client, full_name="Empty Account", email="empty-graph@example.com", password="password12345"
    )
    monkeypatch.setattr(kg_service_module, "get_graph_for_user", MagicMock(return_value=([], [], 0)))

    response = client.get("/kg/graph", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": [], "total_node_count": 0}


def test_get_graph_requires_authentication(client):
    response = client.get("/kg/graph")
    assert response.status_code == 401


def test_get_graph_is_scoped_to_the_calling_account(client, monkeypatch):
    """Account B's request must resolve `user_id` to account B's own id --
    never account A's, and never anything account B's request could supply
    -- confirmed by asserting the exact `user_id` the mocked data-access
    call was invoked with."""
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a-graph@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b-graph@example.com", password="password-account-b"
    )

    fake_get_graph_for_user = MagicMock(return_value=([], [], 0))
    monkeypatch.setattr(kg_service_module, "get_graph_for_user", fake_get_graph_for_user)

    me_response = client.get("/auth/me", headers=_auth_headers(token_b))
    assert me_response.status_code == 200
    account_b_id = me_response.json()["id"]

    response = client.get("/kg/graph", headers=_auth_headers(token_b))

    assert response.status_code == 200
    # No `document_ids` query param sent -- `kg/service.py` forwards an
    # empty list, `get_graph_for_user`'s own unfiltered default.
    fake_get_graph_for_user.assert_called_once_with(account_b_id, [])

    # Same guarantee from account A's side, so this isn't just "whichever
    # account happens to be called last wins."
    me_response_a = client.get("/auth/me", headers=_auth_headers(token_a))
    account_a_id = me_response_a.json()["id"]
    fake_get_graph_for_user.reset_mock()

    client.get("/kg/graph", headers=_auth_headers(token_a))

    fake_get_graph_for_user.assert_called_once_with(account_a_id, [])
    assert account_a_id != account_b_id


def test_get_graph_forwards_document_ids_query_params_to_the_data_access_call(client, monkeypatch):
    """Repeated `?document_ids=<uuid>&document_ids=<uuid>` query params must
    reach `get_graph_for_user` as a plain list of strings -- the Cypher
    layer's own scoping (`_MATCHES_DOCUMENT_SCOPE`), not this route, is what
    actually filters; this just confirms the client's selection reaches it
    intact."""
    token = _register_and_login(
        client, full_name="Scoped Account", email="scoped-graph@example.com", password="password12345"
    )
    fake_get_graph_for_user = MagicMock(return_value=([], [], 0))
    monkeypatch.setattr(kg_service_module, "get_graph_for_user", fake_get_graph_for_user)

    doc_id_a = "11111111-1111-1111-1111-111111111111"
    doc_id_b = "22222222-2222-2222-2222-222222222222"

    response = client.get(
        f"/kg/graph?document_ids={doc_id_a}&document_ids={doc_id_b}",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    (call_args, _) = fake_get_graph_for_user.call_args
    assert call_args[1] == [doc_id_a, doc_id_b]


def test_get_graph_rejects_more_than_200_document_ids(client):
    token = _register_and_login(
        client, full_name="Oversized Selection", email="oversized-graph@example.com", password="password12345"
    )
    doc_ids = "&".join(f"document_ids={i:08x}-0000-0000-0000-000000000000" for i in range(201))

    response = client.get(f"/kg/graph?{doc_ids}", headers=_auth_headers(token))

    assert response.status_code == 422
