"""Limiter coverage for the two question-answering routes.

`POST /chat/sessions/{id}/ask` and `.../messages/{id}/edit` were the only
expensive endpoints in the app with no limiter of any kind -- one `/ask`
costs an OpenRouter routing call, a *metered* Weaviate embedding request
(billed against a cluster-wide free-tier quota, so one account can exhaust
retrieval for every account), and up to two OpenRouter chat completions,
while holding a threadpool worker for the whole span. See
`app/chat/rate_limiter.py` for the full reasoning behind both limits.

The autouse `_fresh_rate_limiters` fixture (conftest.py) deliberately
overrides these with an effectively-unlimited budget so unrelated chat
tests can drive long scripted conversations; the tests here re-override
with a small budget of their own, which is what keeps the limit's actual
behaviour covered without putting every other chat test one question away
from a spurious 429.
"""

import uuid
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.chat import service as chat_service_module
from app.chat.rate_limiter import get_ask_concurrency_limiter, get_ask_rate_limiter
from app.chat.schemas import AskResponse
from app.main import app
from app.shared.rate_limiter import ConcurrencyLimiter, RateLimiter


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


def _create_session_id(client, token):
    response = client.post("/chat/sessions", headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture()
def small_ask_budget():
    """Re-overrides the ask rate limiter with a 3/minute budget for the
    duration of one test, then restores conftest's own override rather
    than clearing the key outright -- `_fresh_rate_limiters` pops its
    dependencies on teardown and must not find them already gone."""
    previous = app.dependency_overrides.get(get_ask_rate_limiter)
    limiter = RateLimiter(
        max_attempts=3, window_seconds=60.0, detail="Too many questions. Try again in a minute."
    )
    app.dependency_overrides[get_ask_rate_limiter] = lambda: limiter
    yield limiter
    if previous is not None:
        app.dependency_overrides[get_ask_rate_limiter] = previous


@pytest.fixture()
def stub_answer(monkeypatch):
    """`/ask` answers instantly with an empty result -- these tests are
    about the limiter, not about retrieval or generation, and neither a
    real Weaviate nor a real OpenRouter may be touched here."""
    monkeypatch.setattr(
        chat_service_module,
        "search_passages",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        chat_service_module,
        "resolve_question",
        Mock(side_effect=lambda question, history: chat_service_module.QuestionPlan(
            intent="factual", search_query=question, reply=None
        )),
    )


def test_ask_returns_429_past_the_window_budget(client, small_ask_budget, stub_answer):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-askratelimit@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    url = f"/chat/sessions/{session_id}/ask"

    # 3/minute is this test's configured budget -- the 4th within the
    # window is the first that must be refused.
    for i in range(3):
        response = client.post(
            url, headers=_auth_headers(token), json={"question": f"question {i}"}
        )
        assert response.status_code == 200, response.text

    refused = client.post(url, headers=_auth_headers(token), json={"question": "one too many"})
    assert refused.status_code == 429
    assert refused.json()["detail"] == "Too many questions. Try again in a minute."


def test_ask_budget_is_per_account_not_global(client, small_ask_budget, stub_answer):
    """The limiter keys on `user_id`, so one account burning its budget
    must never refuse a different account's first question -- the failure
    mode an IP-keyed limiter would have behind a shared NAT."""
    first = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-askscope@example.com", password="password12345"
    )
    first_session = _create_session_id(client, first)
    for i in range(3):
        client.post(
            f"/chat/sessions/{first_session}/ask",
            headers=_auth_headers(first),
            json={"question": f"question {i}"},
        )
    exhausted = client.post(
        f"/chat/sessions/{first_session}/ask",
        headers=_auth_headers(first),
        json={"question": "one too many"},
    )
    assert exhausted.status_code == 429

    second = _register_and_login(
        client, full_name="Ivan Petrov", email="ivan-askscope@example.com", password="password12345"
    )
    second_session = _create_session_id(client, second)
    response = client.post(
        f"/chat/sessions/{second_session}/ask",
        headers=_auth_headers(second),
        json={"question": "my first question"},
    )
    assert response.status_code == 200, response.text


def test_edit_shares_the_same_budget_as_ask(client, small_ask_budget, stub_answer):
    """`edit` re-runs `ask_question` end to end, so it must not carry its
    own separate allowance -- that would just be a second way to spend the
    same upstream quota and threadpool workers."""
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="maria-editshare@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)

    first = client.post(
        f"/chat/sessions/{session_id}/ask",
        headers=_auth_headers(token),
        json={"question": "the original question"},
    )
    assert first.status_code == 200, first.text
    message_id = first.json()["user_message_id"]

    # Two more asks exhaust the 3/minute budget (the ask above was #1).
    for i in range(2):
        assert (
            client.post(
                f"/chat/sessions/{session_id}/ask",
                headers=_auth_headers(token),
                json={"question": f"filler {i}"},
            ).status_code
            == 200
        )

    refused = client.post(
        f"/chat/sessions/{session_id}/messages/{message_id}/edit",
        headers=_auth_headers(token),
        json={"question": "an edited question"},
    )
    assert refused.status_code == 429


def test_ask_concurrency_limiter_rejects_past_max_in_flight():
    """Exercised directly rather than through the TestClient, which issues
    requests synchronously -- no two questions are ever genuinely in
    flight at once through it. Mirrors the upload concurrency test."""
    limiter = ConcurrencyLimiter(max_concurrent=3)
    user_key = "some-user-id"

    with limiter.slot(user_key), limiter.slot(user_key), limiter.slot(user_key):
        # 3 slots held (the configured max) -- the 4th must be refused.
        with pytest.raises(HTTPException) as excinfo:
            with limiter.slot(user_key):
                pass
        assert excinfo.value.status_code == 429

    # All slots released on context exit, and the key dropped rather than
    # left sitting at 0.
    with limiter.slot(user_key):
        pass
    assert user_key not in limiter._in_flight


def test_ask_concurrency_slot_is_released_when_generation_raises():
    """A 503 from generation must not permanently consume a slot -- the
    `with` in `chat/routes.py` is what guarantees that, and this is the
    behaviour that makes it load-bearing rather than stylistic."""
    limiter = ConcurrencyLimiter(max_concurrent=1)
    user_key = "erroring-user"

    with pytest.raises(HTTPException):
        with limiter.slot(user_key):
            raise HTTPException(status_code=503, detail="generation blew up")

    with limiter.slot(user_key):
        pass
    assert user_key not in limiter._in_flight


@pytest.mark.parametrize(
    "path",
    [
        "/chat/sessions/{session_id}/ask",
        "/chat/sessions/{session_id}/messages/{message_id}/edit",
    ],
)
@pytest.mark.parametrize(
    "limiter_dependency", [get_ask_rate_limiter, get_ask_concurrency_limiter]
)
def test_expensive_chat_routes_declare_both_limiters(path, limiter_dependency):
    """Guards against the wiring being dropped in a future refactor while
    the limiter module itself stays in the tree -- which would look like
    coverage without being any.

    Goes through `scripts.isolation_proof`'s own route helpers rather than
    walking `app.routes` directly: this FastAPI version keeps an included
    router as a lazy `_IncludedRouter` instead of flattening it, so a naive
    iteration sees only `/health` and the doc routes and would pass this
    test vacuously by finding no route to check at all.
    """
    from scripts.isolation_proof import _dependency_tree_contains, _iter_effective_routes

    routes = [
        route
        for route in _iter_effective_routes(app.routes)
        if isinstance(route, APIRoute) and route.path == path
    ]
    assert routes, f"{path} is not registered"
    assert _dependency_tree_contains(routes[0].dependant, limiter_dependency)
