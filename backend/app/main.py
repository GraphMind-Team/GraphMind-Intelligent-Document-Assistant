"""FastAPI application entrypoint.

Story 1.1 (running project skeleton): boots the app, wires CORS for the
local frontend dev server, registers each vertical-slice module's (empty)
router, and exposes a neutral `/health` endpoint that isn't owned by any
feature module.

Required environment variables are validated at import time so a missing
var fails fast with a clear error naming it, rather than surfacing later
as a confusing runtime error.
"""

import os

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

app = FastAPI(title="GraphMind API")

# Without this, `request.client.host` (the login/register rate limiters'
# key -- see app.auth.routes) is always the reverse proxy's own IP once
# deployed behind one, since raw TCP peer address is all Starlette sees by
# default. Render's network model puts exactly one hop -- its own edge LB
# -- between the public internet and this app; nothing else can reach it
# directly, so trusting every peer's X-Forwarded-For here is safe. Without
# it, every caller behind the proxy would share one rate-limit budget,
# letting an attacker lock out an arbitrary victim account by burning it
# with unrelated traffic. Locally (no proxy in front of `uvicorn --reload`),
# there's no X-Forwarded-For to trust, so this is a no-op in dev.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

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
