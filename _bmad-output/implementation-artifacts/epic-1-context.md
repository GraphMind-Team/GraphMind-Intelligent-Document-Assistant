# Epic 1 Context: Secure Access & App Foundation

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A visitor can create an account, log in, and trust that their data is structurally isolated from every other user's. This epic also lays the foundation every later epic builds on: the backend and frontend skeletons (there is no starter template, so scaffolding is Day 1 work with no exploratory detours), the design-token system with both light and dark palettes, and the mandatory shared data-access layer that makes tenancy a structural guarantee rather than a convention. Two developers build the `documents` and `chat` modules in parallel from Epic 2 onward against the contracts (Weaviate/Neo4j shapes) established here, so those contracts must be correct even though only the Postgres/auth path is exercised in this epic.

## Stories

- Story 1.1: Running project skeleton
- Story 1.2: Design-token foundation and dual-theme rendering
- Story 1.3: Account registration
- Story 1.4: Login and JWT session
- Story 1.5: Authenticated shell and tenancy-enforced data access

## Requirements & Constraints

- Account creation and login use bcrypt_sha256 password hashing; a JWT is issued on login and sent in the `Authorization` header on every request. No password reset or email verification in v1.
- `user_id` is resolved server-side from the JWT and applied at the data-access layer on every read/write — never trusted from a client-supplied value. This is a launch blocker (cross-tenant leakage), first verified here with two test accounts (re-verified against real documents in Epic 2).
- An expired, malformed, or absent JWT is rejected with 401 before any data access occurs.
- Every route declares a Pydantic `response_model`; every error path returns a plain `HTTPException` → `{"detail": ...}`, no custom error envelope.
- Every secret comes from an environment variable; nothing is committed to the repo.
- Theming (FR-15) is split across epics: this epic builds the full token system, `ThemeContext`, and persistence-ready plumbing so every later screen is theme-aware from the start; the actual Settings toggle UI ships in Epic 5.
- Accessibility floor is WCAG 2.2 AA: status is never colour-only, focus rings must be visible in both themes, tab order follows sidebar → heading → content → secondary panels, and `prefers-reduced-motion` suppresses transitions/progress animation.
- At 200% browser zoom, the fixed-sidebar layout must reflow without horizontal scrolling or clipping; no CSS `order`/`row-reverse` on any layout carrying interactive content, so DOM order and visual order never diverge.
- Copy tone: plain and declarative, no apologetic filler or emoji (sidebar icons excepted).
- Stack is pinned: Python 3.12+, FastAPI 0.141.1, Pydantic v2, SQLAlchemy 2.0.51, Alembic 1.19.0, weaviate-client 4.22.0, neo4j driver 6.2, React 19.2.x, Vite 8.2.1, Tailwind, react-force-graph 1.48.2, JWT + bcrypt.
- This story's Alembic migrations create only the `users` table (Story 1.3); no other table gets created ahead of the story that needs it.

## Technical Decisions

- **Vertical-slice modular monolith.** Backend feature modules `auth`, `documents`, `chat`, `kg`, each with `routes.py` / `service.py` / `repository.py`. Hexagonal/ports-and-adapters explicitly rejected. Cross-module infrastructure lives only in `shared/`.
- **Mandatory shared DAL (`shared/data_access/`)** is the sole path to Weaviate, Neo4j, and Postgres — no feature module hand-writes a raw query. This is the structural mechanism that satisfies the tenancy launch-blocker.
  - Weaviate passage shape is flat, no nested metadata: `chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`.
  - Neo4j entity shape: `name` + `type`, typed relationships between entity references.
  - Any future NL-to-Cypher work must inject `user_id` server-side and never trust LLM-generated output for tenancy filtering (recorded now, not built yet).
- **`shared/llm_client/` (AD-6)** is the sole path to OpenRouter; scaffold it here even though nothing calls it yet in this epic.
- Frontend shared state (auth/user, theme, chat scope) lives in React Context, not Redux.
- Deployment target: frontend on Vercel Hobby, backend on Render free (15-min idle spin-down, ~1 min cold start). Local dev plus one prod environment only, no staging.
- Structural seed: `backend/app/<module>/{routes.py, service.py, repository.py}`, `backend/app/shared/{data_access/, models.py, llm_client/}`, `backend/alembic/versions/`, `frontend/src/{pages/, context/}`.
- Design tokens (light / dark) are the single source of truth for color — no component hardcodes a raw hex value. Five token gaps are explicitly assigned to this epic to close before component work begins elsewhere:
  - Citation chip pair (`#4A7FE0` on `#D1EEFE`) ships as a knowingly accepted AA contrast deviation in light mode — use as specified, do not re-tune. *(Superseded 2026-08-13: closed in Story 3.1 as `#3064C6`/`#D1EEFE`, 4.62:1 — see UX-DR21 in `epics.md`.)*
  - Status-pill background-tint + text pairs must be defined for all five states (Uploaded, Extracting, Graphing, Ready, Failed), each clearing 4.5:1 contrast — only Ready/Uploaded had defined text colors previously (`#0C7A47` / `#8A5200`); the rest still need pairs.
  - A dedicated focus-ring token must be defined, distinct from `border`, clearing 3:1 non-text contrast against `bg`, `surface`, and `surface-dark`, and visible on every interactive element in both themes.
  - `accent` used as link/small-text color (as the reference mockup's `.auth-wrap .switch a` rule does, e.g. the Registration/Login "switch" links) fails 4.5:1 normal-text contrast against `surface` in both themes (~2.85:1 light, ~3.9:1 dark) — found during Story 1.3. `accent` itself isn't wrong (it clears non-text/large-UI thresholds), but it needs either a separate AA-compliant link-text token or a re-check of whether `primary` (already used for headings) reads better as inline link text; the mockup's current choice should not be treated as pre-validated for this use.
  - `danger`/`danger-dark` (`#E01E1E` / `#E4685F`) were tuned and validated against `bg` only (4.80:1 / 4.89:1, per `review-accessibility.md`) — used against `surface`/`surface-dark` instead (e.g. inline form error text inside a `surface`-backed card, the Settings danger-zone card), they drop to 4.24:1 / 4.36:1, just under the 4.5:1 normal-text threshold. Found during Story 1.3, where the Registration error message lives inside a `surface`-backed card. Needs either a re-tune or a separate on-surface danger variant — not re-picked ad hoc per call site.
- Two palettes exist: light "softened baby-blue" (bg `#FFFFFF`, surface `#EDF1FA`, primary `#3861A8`) and dark "Soft Dark" (bg `#1E222B` — a dimmed charcoal, deliberately not near-black — surface `#262B35`, primary `#5B8CFF`). Full token values live in the UX design doc; theme switch via Context must update every rendered surface immediately with no screen left theme-inconsistent.

## UX & Interaction Patterns

- **Authenticated shell:** fixed 220px sidebar + fluid content. Nav order: User Settings, Documents, Chat, Graph Preview, with Exit bottom-anchored and visually separated. Exactly one active nav item at a time.
- Registration and Login pages sit outside the authenticated shell but must still render correctly in both themes.
- Sidebar in light mode is a solid primary-color fill with light link text; in dark mode it switches to the surface-dark tone (not primary), a deliberate asymmetry to avoid a jarring saturated block.
- Logging out via Exit ends the session and returns to Login.

## Cross-Story Dependencies

- Story 1.1 (skeleton) must exist before any other story in this epic or any later epic can add code.
- Story 1.2 (tokens) must land before component-heavy work in later epics (Documents, Chat, Graph, Settings) so no component is built against unstyled or hardcoded colors.
- Story 1.3 (registration) precedes Story 1.4 (login), which precedes Story 1.5 (authenticated shell), since the shell assumes an authenticated session exists.
- Story 1.5's shared DAL and Weaviate/Neo4j shape contracts are a hard dependency for Epic 2's `documents` module and Epic 3's `chat` module, which build against them in parallel — get the shapes right here rather than renegotiating them mid-epic.
- SM-3 (cross-tenant isolation) is first verified in this epic with two test accounts and re-verified against real documents in Epic 2.
- Story 1.3 already built the shared Postgres engine, session factory, and `get_db_session` dependency in `backend/app/shared/data_access/` — Story 1.5 ("authenticated shell and tenancy-enforced data access") should extend this with `user_id`-scoped query patterns and tenancy filtering (AD-2), not rebuild the engine/session layer from scratch.
- Story 1.3 already built a minimal `frontend/src/context/ThemeContext.jsx` (OS `prefers-color-scheme` detection only, no toggle/persistence/setter) and a ~7-variable CSS token subset, scoped to what the Registration page needed. Story 1.2 ("design-token foundation and dual-theme rendering") should extend this — full token set, runtime toggle via the same Context, persistence — not treat theming as unstarted.
