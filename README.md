# GraphMind

Intelligent Document Q&A with Knowledge Graphs

**Live:** [graphmind-web.onrender.com](https://graphmind-web.onrender.com/)

> Hosted on Render's free tier — the backend spins down after 15 minutes idle, so the first request after a period of inactivity can take up to a minute.

GraphMind is a document question-answering assistant that combines vector retrieval with knowledge-graph traversal. Users upload documents; the system builds a per-user knowledge graph alongside a vector index, then answers questions with grounded, cited answers — and explicitly declines to answer when the uploaded documents do not support a claim.

## Problem

Information relevant to a single question is typically scattered across many documents. People spend disproportionate time searching for it, and when an AI assistant does answer, they cannot verify the claim and therefore cannot trust it. GraphMind treats citation and explicit refusal as core product requirements, not optional features.

## How It Works

Two retrieval strategies work together:

- **Vector search** over document passages answers semantic questions ("what does the spec say about the deployment process").
- **Knowledge graph traversal** answers relational questions that require connecting information across documents rather than matching similar text ("which vendors are linked to this project").

Every response is traceable to a specific passage in a specific document. When retrieval finds no adequate supporting evidence, GraphMind returns an explicit "I don't know" rather than guessing from general knowledge.

## Core Capabilities (v1)

- Document ingestion (PDF, Markdown, HTML) with a visible ingestion status (Uploaded → Extracting → Graphing → Ready → Failed) and drag-and-drop upload
- Content-hash deduplication to avoid reprocessing unchanged documents
- A unified per-user knowledge graph, combining entities and relationships extracted across all of a user's documents
- Chat Q&A with structured citations, explicit refusal below an evidence threshold, and document scoping (ask across all documents or a chosen subset). A question-routing step classifies each question into a greeting, a whole-document summary/outline, or a specific factual question, and answers each accordingly — a short conversational reply may accompany an answer, but every factual claim still carries a citation
- Document library: list, inspect, and delete documents, with folders for grouping them
- Read-only knowledge graph visualization
- Per-user authentication and server-side tenancy isolation across every data store
- Light and dark themes, a fully localized interface (English, Bulgarian, German), account management, and account deletion
- An evaluation harness measuring answer accuracy and refusal correctness against a fixed question set

## Architecture

GraphMind is a feature-based modular monolith: each backend module (`auth`, `documents`, `chat`, `kg`) owns its full vertical slice — routing, business logic, and data access — with two shared layers cutting across all of them:

- A **shared data-access layer** is the only path to Weaviate, Neo4j, and Postgres, enforcing per-user tenancy filtering structurally rather than by convention.
- A **shared LLM-client wrapper** is the only path to OpenRouter, centralizing retry/timeout handling and enforcing the refusal short-circuit before any generation call.

Document ingestion writes to Weaviate and Neo4j with a compensating-rollback discipline: if either write fails, whatever the first write already committed is rolled back, so no orphaned data survives a failed ingestion.

A two-page overview of the system and the decisions behind it is in [`ARCHITECTURE.md`](ARCHITECTURE.md). The full normative detail — every invariant with its binding requirement and rationale — lives in the [architecture spine](_bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md).

## Technology Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python) |
| ORM / migrations | SQLAlchemy, Alembic |
| Vector database | Weaviate |
| Graph database | Neo4j AuraDB |
| Relational database | PostgreSQL (Neon) |
| LLM provider | OpenRouter |
| Frontend | React, Vite, Tailwind CSS |
| Graph visualization | force-graph + react-kapsule |
| Authentication | JWT, bcrypt |
| Frontend deployment | Vercel |
| Backend deployment | Render |

All external services run on free tiers, keeping the project reproducible at no cost.

## Project Documentation

This project follows a spec-driven planning process. The full set of planning artifacts lives under `_bmad-output/`:

- **Product requirements**: [`planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md`](_bmad-output/planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md)
- **UX design**: [`planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/`](_bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/) (`DESIGN.md`, `EXPERIENCE.md`, and mockups)
- **Architecture overview**: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **Architecture spine**: [`planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md`](_bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md)
- **Canonical spec**: [`specs/spec-GraphMind-Intelligent-Document-Assistant/SPEC.md`](_bmad-output/specs/spec-GraphMind-Intelligent-Document-Assistant/SPEC.md)

## Local Setup

Requires Python 3.12+ and Node.js `^20.19 || >=22.12` (Vite 8's actual minimum -- a plain "Node 20" install can be older than that and fail to start the frontend). Each developer works from their own local Python virtual environment — there is no shared/global interpreter, and `.venv/` is gitignored.

**Backend**

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in your own local values -- see Configuration below
alembic upgrade head      # create/migrate the Postgres schema
uvicorn app.main:app --reload
```

`.venv` lives in `backend/`, not the repo root -- `.claude/launch.json`'s backend launch config expects it there.

The backend starts on `http://localhost:8000`; `GET /health` returns `{"status": "ok"}`.

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server starts on `http://localhost:5173` and calls the backend `/health` endpoint on load. Optionally copy `frontend/.env.example` to `frontend/.env` to point it at a non-default backend URL.

**Tests & linting**

```bash
cd backend && pytest
cd frontend && npm run lint && npm run test
```

## Configuration & Credentials

Every secret is an environment variable — nothing sensitive is committed. `backend/.env.example` is the authoritative list and carries a detailed comment on each variable; this table is the short version of what you need to obtain before a first run.

| Variable | Required? | Where to get it |
|---|---|---|
| `DATABASE_URL` | **Yes** | A local Postgres, or a free [Neon](https://neon.tech) project. Use the **sync** driver form: `postgresql+psycopg2://...` with `sslmode=require` (not `ssl=require`). |
| `JWT_SECRET` | **Yes** | Generate your own: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The app refuses to boot on anything shorter than 32 bytes. |
| `WEAVIATE_URL`, `WEAVIATE_API_KEY` | **Yes** | A [Weaviate Cloud](https://console.weaviate.cloud) free-tier cluster. It must be a *Cloud* cluster — the app relies on Weaviate Embeddings (`text2vec-weaviate`) to compute vectors and runs no embedding model of its own, so a self-hosted instance will create the collection but never vectorise anything. |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` | **Yes** | A free [Neo4j AuraDB](https://neo4j.com/cloud/aura/) instance. |
| `OPENROUTER_API_KEY` | **Yes** | [openrouter.ai](https://openrouter.ai/keys). The default models are free-tier slugs, so no billing is needed. |
| `OPENROUTER_MODEL`, `OPENROUTER_CHAT_MODEL`, `OPENROUTER_ROUTER_MODEL` | Optional | Overrides for the extraction, chat-answer, and question-routing models. Set one of these if ingestion or chat starts failing with *"This model is unavailable for free"* — OpenRouter withdraws free slugs without notice, and swapping the value here is the intended fix. Pick a replacement from [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0) that lists `response_format` among its supported parameters. |
| `REQUIRE_EMAIL_VERIFICATION` | Optional | Defaults to `true`. **Set it to `false` for a quick local run** — otherwise you need a reachable mailbox to activate a new account. |
| `BREVO_API_KEY` / `SMTP_*` | Optional | Only needed to actually deliver verification email. With none configured, the message (including the verify link) is logged to the console instead — which is what local development and the whole test suite run against. Note that Render's free tier blocks outbound ports 25, 465 and 587, so SMTP cannot work there; Brevo's HTTP API is the production transport. |
| `TRUSTED_PROXY_HOSTS` | Optional | Leave at the default locally. Read the comment in `.env.example` before changing it for a deployment — it governs how the rate limiters recover the real client IP. |
| `VITE_API_BASE_URL` (frontend) | Optional | Defaults to `http://localhost:8000`. |

The fastest path to a working local instance is to set `REQUIRE_EMAIL_VERIFICATION=false`, configure no mail transport, register an account through the UI, and log straight in.

## Seed Data

There is no automatic database seed — a fresh instance starts empty, and you create your own account through the registration screen. Two sets of git-tracked fixture documents are included for evaluating and exercising the system:

- `backend/scripts/eval_fixtures/` — three short Markdown documents (a project brief, a vendor record, a team directory) designed so that answering some questions requires connecting facts across all three.
- `backend/scripts/isolation_fixtures/` — two documents belonging to two different accounts, used by the cross-tenant isolation proof.

You can upload the `eval_fixtures/` files through the UI to get a populated library, knowledge graph, and something meaningful to ask questions about within a minute or two.

**Evaluation harness.** With real credentials in `backend/.env`, this ingests the fixture corpus and runs a fixed 20-question set (factual, synthesis, and deliberately unanswerable) through the real chat service, printing answer accuracy and refusal correctness:

```bash
cd backend && python -m scripts.eval_harness
```

**Cross-tenant isolation proof.** Drives the real FastAPI app with two real registered accounts and genuine bearer tokens — no mocks, no dependency overrides — and checks three things: that every protected route actually requires authentication, that neither account can reach the other's documents, answers, or graph entities, and that forged tokens — and validly-signed tokens for accounts that no longer exist — are rejected everywhere. It needs `ISOLATION_QA1_PASSWORD` and `ISOLATION_QA2_PASSWORD` set:

```bash
cd backend && python -m scripts.isolation_proof
```

Both scripts talk to the real Weaviate / Neo4j / OpenRouter / Postgres configured in `backend/.env` — that is deliberate, since a mocked run would prove nothing. They fail loudly on missing configuration rather than silently.

## Project Context

GraphMind is being built by a two-person team over a 20-day delivery window, scoped deliberately to a strict MVP following KISS and YAGNI principles. Later phases are tracked separately and are not part of the v1 deliverable.

## Status

Feature-complete against the v1 scope. All six epics — foundation and auth, document ingestion, grounded chat, knowledge-graph visualization, account settings, and the evaluation/isolation harnesses — are implemented and deployed. Work intentionally left out of v1, along with the reasoning, is tracked in [`deferred-work.md`](_bmad-output/implementation-artifacts/deferred-work.md).
