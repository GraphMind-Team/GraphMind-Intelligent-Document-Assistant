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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router
from app.documents.routes import router as documents_router
from app.kg.routes import router as kg_router

# Populate os.environ from backend/.env if present (local dev convenience).
# In deployment, real env vars are injected by the platform instead.
load_dotenv()

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
