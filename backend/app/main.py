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
from app.kg.routes import router as kg_router
from app.shared.data_access.neo4j_client import close_neo4j_driver, ensure_ready as ensure_neo4j_ready
from app.shared.data_access.weaviate_client import close_weaviate_client, ensure_ready

logger = logging.getLogger(__name__)

REQUIRED_ENV_VARS = ["DATABASE_URL", "JWT_SECRET"]


def _validate_env() -> None:
    """Fail fast at startup if a required environment variable is absent."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. See backend/.env.example."
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
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(kg_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
