"""FastAPI application entrypoint.

Story 1.1 (running project skeleton): boots the app, wires CORS for the
local frontend dev server, registers each vertical-slice module's (empty)
router, and exposes a neutral `/health` endpoint that isn't owned by any
feature module.

Required environment variables are validated at import time so a missing
var fails fast with a clear error naming it, rather than surfacing later
as a confusing runtime error.
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Populate os.environ from backend/.env if present (local dev convenience),
# before importing any module below -- `auth.routes` transitively imports
# `shared.data_access.session`, which reads DATABASE_URL at import time. In
# deployment, real env vars are injected by the platform instead.
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router
from app.documents.routes import router as documents_router
from app.folders.routes import router as folders_router
from app.kg.routes import router as kg_router
from app.shared.data_access.neo4j_client import close_neo4j_driver, ensure_ready as ensure_neo4j_ready
from app.shared.data_access.weaviate_client import close_weaviate_client, ensure_ready

logger = logging.getLogger(__name__)

REQUIRED_ENV_VARS = ["DATABASE_URL", "JWT_SECRET"]

# RFC 7518 section 3.2: an HMAC-SHA256 key must be at least as long as the
# hash output, i.e. 256 bits / 32 bytes. Shorter secrets are not rejected
# by PyJWT -- it signs and verifies with them perfectly happily, only
# emitting an `InsecureKeyLengthWarning` that nothing in a deployed process
# is watching -- so a weak `JWT_SECRET` is silently accepted and every
# token in the system inherits its strength. Checked here because this
# function already exists to turn exactly this class of misconfiguration
# into a loud failure at boot rather than a quiet weakness in production.
_MIN_JWT_SECRET_BYTES = 32

# Optional, unlike REQUIRED_ENV_VARS above: absent is fine, since both have
# defaults in `auth/service.py`. What is not fine is a value that is present
# but cannot be honoured, because both become a JWT lifetime.
#
# Zero or negative mints a token already expired when issued: login answers
# 200 and `/auth/me` immediately 401s, an endless sign-in loop with nothing
# in the logs naming the cause. `int()` accepts "0" and "-30" without
# complaint, so the `ValueError` guard those getters already had never saw
# them.
#
# Unparseable is rejected here too, rather than left to the silent fallback.
# `ACCESS_TOKEN_EXPIRE_MINUTES=1440m` quietly yielding 60 is a session
# twenty-four times shorter than the operator configured, with no signal
# that anything was ignored -- the same silent-wrongness this check exists
# to end, just wearing a different value.
_POSITIVE_INT_ENV_VARS = ("ACCESS_TOKEN_EXPIRE_MINUTES", "EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS")


def _validate_env() -> None:
    """Fail fast at startup if a required environment variable is absent,
    or if `JWT_SECRET` is present but too weak to sign HS256 tokens with."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. See backend/.env.example."
        )

    # Length in *bytes*, not characters: a non-ASCII secret encodes to more
    # bytes than it has characters, and the byte string is what actually
    # keys the HMAC. Never logs or echoes the value itself -- only its
    # length -- since a startup traceback is one of the easier things to
    # end up in a shared log.
    secret_bytes = len(os.environ["JWT_SECRET"].strip().encode("utf-8"))
    if secret_bytes < _MIN_JWT_SECRET_BYTES:
        raise RuntimeError(
            f"JWT_SECRET is too short: {secret_bytes} bytes, minimum "
            f"{_MIN_JWT_SECRET_BYTES} (RFC 7518 section 3.2 for HS256). "
            "Generate one with: python -c \"import secrets; "
            'print(secrets.token_urlsafe(32))"'
        )

    for name in _POSITIVE_INT_ENV_VARS:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue  # absent or blank -- the code default applies, which is fine
        try:
            value = int(raw)
        except ValueError:
            raise RuntimeError(
                f"{name} must be a positive whole number of "
                f"{'minutes' if name.endswith('MINUTES') else 'hours'}; got {raw!r}."
            ) from None
        if value <= 0:
            raise RuntimeError(
                f"{name} must be positive; got {value}. A zero or negative lifetime "
                "issues tokens that are already expired when they are created."
            )


_validate_env()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort: connects and ensures the Passage collection exists
    # once, before the app starts serving requests, so concurrent uploads
    # racing to create it can't happen in the common case (see
    # weaviate_client.ensure_ready's docstring). Not required for the app
    # to boot -- Weaviate being unconfigured/unreachable here must not
    # crash startup, since ingestion already degrades to `Failed` per
    # document rather than needing Weaviate up-front.
    try:
        ensure_ready()
    except Exception:
        logger.exception("Weaviate not ready at startup -- ingestion will degrade to Failed")

    # Same best-effort treatment as Weaviate above: creates the `:Entity`
    # (name, type, user_id) uniqueness constraint if the deployment
    # supports it. Not required for the app to boot -- Neo4j being
    # unconfigured/unreachable, or the constraint being unsupported on a
    # Community-tier deployment, must not crash startup (see
    # neo4j_client.ensure_ready's docstring).
    try:
        ensure_neo4j_ready()
    except Exception:
        logger.exception("Neo4j not ready at startup -- ingestion will degrade to Failed")

    # There is deliberately no embedding-model warmup here any more. The
    # app used to load fastembed's multilingual MiniLM in a daemon thread
    # at startup, which cost ~554MB resident and OOM-restarted the service
    # on Render's 512MB free instance on *every* boot -- whether or not
    # anyone ever asked a question. Weaviate now embeds server-side
    # (text2vec-weaviate), so this process holds no model to warm.
    yield

    close_weaviate_client()
    # Symmetric with the Weaviate client above -- safe to call unconditionally
    # even if no document ever reached Story 2.4's Graphing step this run.
    close_neo4j_driver()


app = FastAPI(title="GraphMind API", lifespan=lifespan)

# Without this, `request.client.host` (the login/register rate limiters'
# key -- see app.auth.routes) is always the reverse proxy's own IP once
# deployed behind one, since raw TCP peer address is all Starlette sees by
# default. Every caller behind the proxy would then share one rate-limit
# budget, letting an attacker lock out an arbitrary victim account by
# burning it with unrelated traffic.
#
# `trusted_hosts` gates *which* immediate TCP peer is allowed to hand us a
# X-Forwarded-For value we then believe -- trusting everyone (`"*"`) would
# let anyone who can open a direct connection to this process (bypassing
# the proxy) hand us an arbitrary spoofed IP, defeating the rate limiter
# more thoroughly than the unpatched version did. Defaults to loopback
# only, so this is inert both in local dev (no proxy in front of `uvicorn
# --reload`, nothing to trust) and, left unset, in production too --
# see backend/.env.example for why that's a real production risk (not a
# hypothetical) that needs a deliberate deploy-time decision, not a value
# this default can safely guess at.
TRUSTED_PROXY_HOSTS = os.environ.get("TRUSTED_PROXY_HOSTS", "127.0.0.1")
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=TRUSTED_PROXY_HOSTS)

# Local frontend dev server origin (Vite default port).
#
# `.strip() or <default>`, not `os.environ.get(KEY, <default>)`: the
# two-arg form returns its default only when the key is ABSENT, so a key
# that exists but is empty yields `""` -- and `allow_origins=[""]` matches
# no origin at all, silently rejecting every cross-origin request
# including the localhost one this default exists to permit. That is not a
# hypothetical: deploying the backend before the frontend URL exists means
# setting this blank on purpose, which is exactly the state that produces
# it. The failure surfaces only in a browser, as a CORS error naming an
# origin that looks correct in the dashboard, with the server logging
# nothing -- so it is worth spending a `.strip()` to make blank behave
# like unset.
#
# `.rstrip("/")` for the neighbouring trap: a browser's `Origin` header is
# scheme://host[:port] with no trailing slash, so a pasted
# "https://example.com/" would never match either, and fails identically.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "").strip().rstrip("/") or "http://localhost:5173"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(folders_router)
app.include_router(chat_router)
app.include_router(kg_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
