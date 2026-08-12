<!-- bmad:context -->
<!-- Verified 2026-08-12 against 6f252e13eaed1e40964aa85a1cb6820087d3b16f. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## GraphMind

Document Q&A assistant combining vector retrieval (Weaviate) with knowledge-graph traversal (Neo4j), answering with citations and explicit refusal when evidence is insufficient. Backend: FastAPI/Python feature-based modular monolith (`auth`, `documents`, `chat`, `kg` modules). Frontend: React/Vite/Tailwind. No application code exists yet — architecture and spec are finalized, implementation has not started. Full planning docs under `_bmad-output/`.

## Policy

- Never write a raw Weaviate or Neo4j query outside `shared/data_access/` — it is the only path that enforces per-user tenancy filtering; a hand-written query is a tenancy-isolation defect (AD-2).
- Never call OpenRouter outside `shared/llm_client/` — it is the sole enforcement point for the refusal short-circuit before generation (AD-6).
- Never commit secrets; env vars only, no staging tier, one deployed prod environment (AD-8).

## Where things are

- Architecture spine (all invariants AD-1..AD-9, stack, deployment topology, structural seed): `_bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md`
- PRD: `_bmad-output/planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md`
- UX design: `_bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/`
- Canonical spec: `_bmad-output/specs/spec-GraphMind-Intelligent-Document-Assistant/SPEC.md`
- Epics/stories: `_bmad-output/planning-artifacts/epics.md`
- Planned structure once code lands: `backend/app/<module>/{routes.py, service.py, repository.py}` per module (`auth`, `documents`, `chat`, `kg`); shared infra in `backend/app/shared/{data_access/, llm_client/}`; frontend in `frontend/src/{pages/, context/}`.

## Conventions that differ from defaults

- Modules are vertical slices (`auth/`, `documents/`, `chat/`, `kg/`, each owning its own `routes.py`/`service.py`/`repository.py`), not horizontal layers — avoid creating repo-wide `routers/`, `services/`, `repositories/` directories.
- Frontend shared state (auth/user, theme, chat document-scope) goes in React Context, never Redux (AD-5).
- All route error responses use FastAPI's default `HTTPException` → `{"detail": ...}`; no custom error envelope (AD-3).
- Knowledge-graph entity merge is exact string match only — never introduce fuzzy or LLM-assisted merge in v1 (AD-4).
- Ingestion write order is fixed: Weaviate write, then Neo4j write. On a Neo4j failure, delete the just-written Weaviate objects before marking the document `Failed` (AD-1).

<!-- /bmad:context -->
