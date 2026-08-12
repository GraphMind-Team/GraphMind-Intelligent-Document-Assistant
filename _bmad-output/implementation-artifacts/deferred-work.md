- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-running-project-skeleton.md`
  summary: Add a CI workflow (`.github/workflows/`) running backend lint/tests and frontend lint/build on push/PR.
  evidence: Story 1.1 review (blind-hunter) found no CI configuration exists; not required to prove the skeleton runs locally, but the project has no automated gate before merge going forward.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-running-project-skeleton.md`
  summary: Add a fetch timeout / abort signal to `HealthPage.jsx` so a hung backend request doesn't leave the UI stuck on "loading" forever.
  evidence: Story 1.1 review (edge-case-hunter) found no timeout on the health-check fetch; low likelihood on localhost, real gap once deployed to Render's free tier with cold starts.

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 1.3: Account registration)
  summary: Add a `vercel.json` SPA rewrite (catch-all to `index.html`) before the frontend is first deployed to Vercel.
  evidence: Story 1.3 introduced client-side routing (`react-router-dom`/`BrowserRouter`) for the Registration page. `epic-1-context.md` pins the frontend deployment target to Vercel. Without a rewrite rule, a direct load or refresh on any non-root route (e.g. `/health`, later `/register`, `/login`) 404s on Vercel's static host — Vite's local dev server serves it correctly, so this doesn't show up until the first real deploy. Not a blocker now (nothing is deployed yet).

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-design-token-foundation-and-dual-theme-rendering.md`
  summary: Set the `color-scheme` CSS property (`light`/`dark`) alongside `data-theme` so native form controls and scrollbars match the theme.
  evidence: Story 1.2 review (blind-hunter) found no `color-scheme` handling; no native form inputs exist yet (Story 1.3/1.4 add the first ones), so there's nothing to visibly regress until then.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-authenticated-shell-and-tenancy-enforced-data-access.md`
  summary: Set up frontend test tooling (vitest + React Testing Library) and cover `ProtectedRoute`/`PublicOnlyRoute`/`Shell`'s Exit handler and `LoginPage`'s redirect-target logic -- the client-side auth-gating/redirect logic this story introduces has zero automated coverage.
  evidence: Story 1.5 review (blind-hunter + verification-gap, independently, across two review passes) found no frontend test runner anywhere in the repo. Verification-gap specifically traced that a `ProtectedRoute`/`PublicOnlyRoute` condition inversion (locking every user out, or exposing every shell/auth route to the wrong audience) would ship with no automated signal. Every behavior was manually verified live in-browser for this story, but that doesn't survive the next change to these files. Worth prioritizing alongside/before the CI-workflow item above, since this gap is security-adjacent rather than cosmetic.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-authenticated-shell-and-tenancy-enforced-data-access.md`
  summary: Give `RegisterPage`'s post-success state a "Log in now" link (or auto-login) instead of leaving the user stranded on a static confirmation message.
  evidence: Story 1.5 review (blind-hunter) noted this is now a UX inconsistency relative to the login flow's new redirect-back smoothness. Pre-existing from Story 1.3, not introduced by 1.5 -- out of this story's scope, but cheap to fix whenever Register/Login next get touched.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-authenticated-shell-and-tenancy-enforced-data-access.md`
  summary: Extract `LoginPage`/`RegisterPage`'s shared card/logo-mark/input markup into a common `AuthCard` component -- the two pages are now near-identical after this story's mockup-matching pass.
  evidence: Story 1.5 review (blind-hunter) flagged the duplication; any future visual change (theme, spacing) needs to be applied in both files today.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-authenticated-shell-and-tenancy-enforced-data-access.md`
  summary: Decide a unique-id scheme for `Neo4jEntity`/`Neo4jRelationship` (currently keyed by `name`, per epics.md's literal AC text) before Epic 2/3/4 build real extraction against `shapes.py` -- two distinct entities sharing a display name (e.g. two people named "John Smith") are currently indistinguishable. Consider timestamp fields (`created_at`) at the same time.
  evidence: Story 1.5 review (blind-hunter) raised this; the shape as documented matches the epic's own AC text exactly, so resolving it is a product/architecture decision for whoever picks up Epic 2's entity-extraction work (ties into the already-tracked OD-1 open decision on the entity/relationship type list), not a bug in this story.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-authenticated-shell-and-tenancy-enforced-data-access.md`
  summary: Set `document.title` per route (Documents/Chat/Graph/Settings/Login/Register currently all share one static title).
  evidence: Story 1.5 review (blind-hunter) noted this as a minor but real bookmarking/browser-history legibility gap for the now-multi-page shell.
