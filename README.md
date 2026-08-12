# GraphMind

Intelligent Document Q&A with Knowledge Graphs

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
- Chat Q&A with structured citations, explicit refusal below an evidence threshold, and document scoping (ask across all documents or a chosen subset)
- Document library: list, inspect, and delete documents
- Read-only knowledge graph visualization
- Per-user authentication and server-side tenancy isolation across every data store
- Light and dark themes, account management, and account deletion
- An evaluation harness measuring answer accuracy and refusal correctness against a fixed question set

## Architecture

GraphMind is a feature-based modular monolith: each backend module (`auth`, `documents`, `chat`, `kg`) owns its full vertical slice — routing, business logic, and data access — with two shared layers cutting across all of them:

- A **shared data-access layer** is the only path to Weaviate, Neo4j, and Postgres, enforcing per-user tenancy filtering structurally rather than by convention.
- A **shared LLM-client wrapper** is the only path to OpenRouter, centralizing retry/timeout handling and enforcing the refusal short-circuit before any generation call.

Document ingestion writes to Weaviate and Neo4j with a compensating-rollback discipline: if either write fails, whatever the first write already committed is rolled back, so no orphaned data survives a failed ingestion.

Full technical detail — invariants, stack, deployment topology, and source layout — lives in the architecture spine: [`_bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md`](_bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md).

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
| Graph visualization | react-force-graph |
| Authentication | JWT, bcrypt |
| Frontend deployment | Vercel |
| Backend deployment | Render |

All external services run on free tiers, keeping the project reproducible at no cost.

## Project Documentation

This project follows a spec-driven planning process. The full set of planning artifacts lives under `_bmad-output/`:

- **Product requirements**: [`planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md`](_bmad-output/planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md)
- **UX design**: [`planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/`](_bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/) (`DESIGN.md`, `EXPERIENCE.md`, and mockups)
- **Architecture**: [`planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md`](_bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md)
- **Canonical spec**: [`specs/spec-GraphMind-Intelligent-Document-Assistant/SPEC.md`](_bmad-output/specs/spec-GraphMind-Intelligent-Document-Assistant/SPEC.md)

## Local Setup

Requires Python 3.12+ and Node.js `^20.19 || >=22.12` (Vite 8's actual minimum -- a plain "Node 20" install can be older than that and fail to start the frontend). Each developer works from their own local Python virtual environment — there is no shared/global interpreter, and `.venv/` is gitignored.

**Backend**

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own local values
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

## Project Context

GraphMind is being built by a two-person team over a 20-day delivery window, scoped deliberately to a strict MVP following KISS and YAGNI principles. Later phases are tracked separately and are not part of the v1 deliverable.

## Status

In development. Architecture and specification are finalized; implementation is in progress.
