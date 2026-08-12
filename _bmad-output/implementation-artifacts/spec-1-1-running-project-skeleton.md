---
title: 'Story 1.1: Running project skeleton'
type: 'feature'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '6f252e13eaed1e40964aa85a1cb6820087d3b16f'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** No application code exists yet. There is no starter template, so backend and frontend scaffolding, module layout, and per-developer dependency setup must be decided and built before any feature story can add behavior.

**Approach:** Scaffold a FastAPI backend (vertical-slice modules `auth`, `documents`, `chat`, `kg`, each with `routes.py`/`service.py`/`repository.py`, plus `shared/data_access/`, `shared/models.py`, `shared/llm_client/`, `alembic/versions/`) and a React/Vite/Tailwind frontend, wired so the frontend calls a backend health endpoint and renders the response. Dependencies are declared in a pinned `backend/requirements.txt`, installed by each developer into their own local `.venv` (already gitignored) — never a shared/global interpreter.

## Boundaries & Constraints

**Always:**
- Follow the structural seed exactly: `backend/app/<module>/{routes.py, service.py, repository.py}` for `auth`, `documents`, `chat`, `kg`; `backend/app/shared/{data_access/, models.py, llm_client/}`; `backend/alembic/versions/`; `frontend/src/{pages/, context/}`.
- Pin dependency versions exactly per the architecture's stack table: FastAPI 0.141.1, Pydantic v2, SQLAlchemy 2.0.51, Alembic 1.19.0, weaviate-client 4.22.0, neo4j 6.2, React 19.2.x, Vite 8.2.1, react-force-graph 1.48.2. Python 3.12+.
- Each developer installs backend dependencies with `pip install -r backend/requirements.txt` into their own local `.venv` at the repo root (already in `.gitignore`); document this exact command in the README so both teammates set up identically without a shared environment.
- Every route declares a Pydantic `response_model`; every error path is a plain `HTTPException` → `{"detail": ...}`.
- Every module directory that owns no logic yet still gets stub `routes.py`/`service.py`/`repository.py` files (empty router registration is fine) so the directory shape is correct from day one — do not defer directory creation to the story that first needs it.
- Secrets (DB URL, JWT secret, API keys) load from environment variables only, via a `.env.example` template committed to the repo — never a committed `.env`.
- Health endpoint lives in a neutral location (e.g. `backend/app/main.py`), not inside a feature module, since it isn't feature-owned.

**Ask First:** Whether to also scaffold `docker-compose` or any containerization — not requested by the story; skip unless the human asks.

**Never:**
- Do not create any Postgres table beyond what's strictly needed to prove the skeleton boots (this story creates no tables at all — `users` arrives in Story 1.3's migration, not here).
- Do not add authentication, business logic, or real Weaviate/Neo4j/OpenRouter calls in this story — modules are structurally present but empty.
- Do not use poetry, pipenv, conda, or any dependency manager other than `pip` + `requirements.txt` + `venv` — keep it the simplest tool that satisfies "each developer has their own isolated environment."

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh clone, backend setup | Developer runs `pip install -r backend/requirements.txt` inside their own activated `.venv` | All pinned dependencies install without conflicts; `uvicorn` runs the app | N/A |
| Health check | Frontend dev server calls backend `/health` | Backend returns 200 with a Pydantic-modeled JSON body; frontend renders it | If backend unreachable, frontend shows a visible fetch error, not a silent blank screen |
| Missing env var at startup | Required env var absent | App fails fast with a clear startup error naming the missing var | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/main.py` -- new: FastAPI app instance, CORS config for local frontend origin, mounts module routers, defines `/health`
- `backend/app/auth/`, `backend/app/documents/`, `backend/app/chat/`, `backend/app/kg/` -- new: each gets stub `routes.py` (empty/no-op `APIRouter`), `service.py`, `repository.py`
- `backend/app/shared/data_access/` -- new: empty package, docstring noting AD-2 (sole path to Weaviate/Neo4j/Postgres) for future stories
- `backend/app/shared/models.py` -- new: SQLAlchemy `Base` declarative setup, no models yet
- `backend/app/shared/llm_client/` -- new: empty package, docstring noting AD-6 (sole path to OpenRouter) for future stories
- `backend/alembic/` -- new: `alembic init`-generated structure wired to `shared/models.py` metadata, `versions/` empty
- `backend/requirements.txt` -- new: pinned dependency list per architecture stack table
- `backend/.env.example` -- new: documents required env vars (`DATABASE_URL`, `JWT_SECRET`, etc.) with placeholder values
- `frontend/` -- new: Vite + React 19 + Tailwind scaffold, `src/pages/`, `src/context/`, one page fetching and rendering the backend `/health` response
- `README.md` -- edit: add a "Local Setup" section covering per-developer `.venv` creation + `pip install -r backend/requirements.txt`, and frontend `npm install`/`npm run dev`

## Tasks & Acceptance

**Execution:**
- [x] `backend/requirements.txt` -- pin all backend dependencies from the stack table -- reproducible installs across both developers' venvs
- [x] `backend/app/main.py` -- create FastAPI app, CORS, `/health` route with Pydantic `response_model` -- proves backend boots and is callable
- [x] `backend/app/{auth,documents,chat,kg}/{routes,service,repository}.py` -- create stub files, register empty routers in `main.py` -- matches structural seed and AC for module inspection
- [x] `backend/app/shared/{data_access/,models.py,llm_client/}` -- create per structural seed -- future stories build on these without renegotiating layout
- [x] `backend/alembic/` -- init Alembic pointed at `shared/models.py` metadata, no migrations yet -- ready for Story 1.3's `users` table
- [x] `backend/.env.example` -- list required env vars with placeholders -- secrets never hardcoded (AD-8)
- [x] `frontend/` -- scaffold Vite+React+Tailwind, one page calling backend `/health` and rendering the response -- proves frontend/backend integration end-to-end
- [x] `README.md` -- add "Local Setup" section: create `.venv`, activate it, `pip install -r backend/requirements.txt`, `npm install` in `frontend/`, run both dev servers -- lets each developer set up independently and identically

**Acceptance Criteria:**
- Given a clean checkout, when a developer creates their own `.venv` and runs `pip install -r backend/requirements.txt` followed by `uvicorn app.main:app --reload`, then the backend starts locally with no dependency conflicts.
- Given the backend running, when the frontend dev server starts and loads its main page, then it calls `/health` and renders the response on screen.
- Given the backend project structure, when inspected, then `auth/`, `documents/`, `chat/`, `kg/` each contain `routes.py`, `service.py`, `repository.py`, and `shared/data_access/` + `shared/llm_client/` exist as the only infra paths.
- Given any route in the skeleton, when it returns success, then it declares a Pydantic `response_model`; any error path returns `HTTPException` → `{"detail": ...}`.
- Given the repo's `.gitignore`, when `.venv/` is checked, then it is excluded from version control for both developers.

## Design Notes

Two developers, two independent `.venv` directories at the same relative path (`.venv/` at repo root, already gitignored) — `requirements.txt` is the single shared source of truth for versions so both environments stay identical without either person touching the other's virtualenv.

## Verification

**Commands:**
- `pip install -r backend/requirements.txt` -- expected: completes with no version-resolution errors, run inside an activated `.venv`
- `uvicorn app.main:app --reload` (from `backend/`) -- expected: server starts, `GET /health` returns 200
- `npm run dev` (from `frontend/`) -- expected: dev server starts, page renders backend health response without console errors
- `pytest` (from `backend/`) -- expected: `test_health.py` passes, asserting `/health` returns 200 and `{"status": "ok"}`

**Manual checks (if no CLI):**
- Confirm `.venv/` does not appear in `git status` after install.

## Suggested Review Order

**Backend entry point & fail-fast config**

- Env vars validated before the app object exists, so a missing var fails at import, not on first request.
  [`main.py:29`](../../backend/app/main.py#L29)

- The neutral `/health` route this whole story exists to prove — lives outside any feature module.
  [`main.py:63`](../../backend/app/main.py#L63)

- Each empty module router still gets registered so the app boots with the full structural seed present.
  [`main.py:57`](../../backend/app/main.py#L57)

**Database migrations wiring**

- Alembic now fails fast on a missing `DATABASE_URL`, matching `main.py`'s pattern, instead of a confusing downstream SQLAlchemy error.
  [`env.py:34`](../../backend/alembic/env.py#L34)

**Frontend integration**

- Base URL resolution deliberately uses `||`, not `??`, so an empty-string env override still falls back to the default.
  [`HealthPage.jsx:3`](../../frontend/src/pages/HealthPage.jsx#L3)

- The one fetch call this story's AC hinges on — cancel-on-unmount guard included.
  [`HealthPage.jsx:17`](../../frontend/src/pages/HealthPage.jsx#L17)

- Wires `HealthPage` as the app's only page for now.
  [`App.jsx:1`](../../frontend/src/App.jsx#L1)

**Dependency pinning**

- Backend dependencies pinned to the architecture's stack table; `psycopg2-binary` is the sync driver, matching Alembic's default sync migration setup (no async DB I/O anywhere in this skeleton yet).
  [`requirements.txt:1`](../../backend/requirements.txt#L1)

- `DATABASE_URL` documented with the sync scheme (`postgresql+psycopg2://`) and `sslmode=require` (Neon's async-driver strings use `ssl=require` instead -- not interchangeable).
  [`.env.example:5`](../../backend/.env.example#L5)

**Tests & docs (peripherals)**

- Only test in the skeleton: pins down the one contract (`/health` → `{"status": "ok"}`) this story is meant to prove.
  [`test_health.py:1`](../../backend/tests/test_health.py#L1)

- Required env vars are set here, before `app.main` is ever imported by a test.
  [`conftest.py:1`](../../backend/tests/conftest.py#L1)

- Local Setup section documents per-developer `.venv` + `requirements.txt` install, matching the venv workflow this story was built around.
  [`README.md:70`](../../README.md#L70)
