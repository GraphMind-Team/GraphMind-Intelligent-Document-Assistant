# Epic 5 Context: Account & Appearance Settings

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A user can manage their profile, change their password, switch the application's light/dark appearance, and permanently delete their account with full confidence about what is removed. This epic is sequenced after Epic 2 because account deletion's cascade has nothing to clean up until documents and graph entities exist.

## Stories

- Story 5.1: Manage my profile and password
- Story 5.2: Choose light or dark appearance and have it remembered
- Story 5.3: Delete my account and everything in it

## Requirements & Constraints

- Password change is an in-session change from an authenticated user, not a forgot-password/reset flow — reset/email-verification remains out of v1 scope.
- New passwords are hashed with `bcrypt_sha256`, the same scheme used at registration.
- Theme preference (FR-15) is a manual choice only — no OS-preference auto-detection in v1 — and persists against the user's account (not just the browser), so it survives logout/login and applies immediately app-wide, including on Login/Registration pages.
- Account deletion (FR-16) requires an explicit confirmation step before anything is removed; on confirm it is immediate and final with no recovery/undo window, and the user is logged out immediately afterward.
- Account deletion hard-deletes the user's Postgres rows, all Weaviate objects, and all Neo4j entities/relationships for that user.
- All four settings cards (Profile, Change Password, Appearance, Delete Account) save independently — saving one never requires touching another.
- Validation/error responses on these cards use FastAPI's default `HTTPException` → `{"detail": ...}` shape; no custom error envelope. Messages must be plain, declarative, and specific about why (no hedging, no apologetic filler).

## Technical Decisions

- **AD-2 (mandatory shared data-access layer):** all reads/writes to Weaviate, Neo4j, and Postgres go through `shared/data_access/`; no module hand-writes raw queries. Account deletion's cascade must go through this same layer, not a special-cased raw-query path.
- **AD-3 (API contract):** every route declares a Pydantic `response_model` for success; every error path uses `HTTPException(status_code, detail)`.
- **AD-5 (frontend state):** shared frontend state — including theme preference — lives in React Context, not Redux or another state library.
- **AD-9 (cascade delete):** on confirmed deletion, hard-delete Postgres row(s), all Weaviate objects, and all Neo4j entities/relationships via the shared DAL. If the deletion partially fails across stores, it follows the same compensating-rollback discipline as ingestion (AD-1) — a silent partial delete is never allowed to stand. The deletion path only ever performs a full cascade of all of a user's rows at once; it never partially or concurrently mutates a document's ingestion-status field, since that field is solely owned by the `documents` module (AD-1). This keeps ingestion and account-deletion ownership non-conflicting.
- Settings lives in the `auth` module for account-related concerns (profile, password, deletion) and in frontend `context/` for theme.

## UX & Interaction Patterns

- Settings page renders four independent cards in a two-column grid at 900px max width: Profile, Change Password, Appearance, Delete Account. Each card follows the base card style (surface fill, 1px border, 12px radius); the Delete Account card additionally uses a danger-tinted border/background, visually separated as a "danger zone."
- Appearance card shows a two-state toggle switch: 40×22px pill track, border color when off, primary color when on, white thumb.
- Delete Account confirmation follows the same danger-zone/explicit-confirm pattern already established for document delete — never a single click to destroy data. Cancel and Confirm must both be reachable and clearly labeled for keyboard and screen-reader users; neither may depend on hover or a pointer-only affordance.
- Error/validation copy on settings cards must be plain and declarative, consistent with the product's overall brand voice (plain, specific about why — especially around deletion boundaries).

## Cross-Story Dependencies

- Story 5.2's theme Context (AD-5) must apply correctly to every screen in the app, including Login/Registration, so it has UI implications beyond the Settings page itself.
- Story 5.3's cascade delete depends on the same shared DAL and rollback discipline used by document ingestion (AD-1/AD-2), so it is not purely local to the `auth` module.
