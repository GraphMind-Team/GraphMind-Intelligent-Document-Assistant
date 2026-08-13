- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-running-project-skeleton.md`
  summary: Add a CI workflow (`.github/workflows/`) running backend lint/tests and frontend lint/build on push/PR.
  evidence: Story 1.1 review (blind-hunter) found no CI configuration exists; not required to prove the skeleton runs locally, but the project has no automated gate before merge going forward.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-running-project-skeleton.md`
  summary: Add a fetch timeout / abort signal to `HealthPage.jsx` so a hung backend request doesn't leave the UI stuck on "loading" forever.
  evidence: Story 1.1 review (edge-case-hunter) found no timeout on the health-check fetch; low likelihood on localhost, real gap once deployed to Render's free tier with cold starts.

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 1.3: Account registration)
  summary: Add a `vercel.json` SPA rewrite (catch-all to `index.html`) before the frontend is first deployed to Vercel.
  evidence: Story 1.3 introduced client-side routing (`react-router-dom`/`BrowserRouter`) for the Registration page. `epic-1-context.md` pins the frontend deployment target to Vercel. Without a rewrite rule, a direct load or refresh on any non-root route (e.g. `/health`, later `/register`, `/login`) 404s on Vercel's static host — Vite's local dev server serves it correctly, so this doesn't show up until the first real deploy. Not a blocker now (nothing is deployed yet).

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

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-authenticated-shell-and-tenancy-enforced-data-access.md`
  summary: >
    Before the first Render deploy (Epic 2+): set `TRUSTED_PROXY_HOSTS` (backend env var,
    `backend/app/main.py`) to a real value. Left at its safe default (`127.0.0.1`), every
    caller's `request.client.host` resolves to Render's edge proxy IP once actually deployed
    behind one -- login degrades to the old per-email lockout risk (findings this env var was
    added to fix), and `/auth/register`'s IP-only rate-limit key becomes a single shared
    5-per-60s budget for the entire site, not per caller. Render doesn't publish a stable
    IP/CIDR for its edge proxy, so "*" is the only practical value -- but only after confirming
    (current Render docs at deploy time) that this app's container has no direct public port
    and is reachable only through Render's own routing layer. Setting "*" without that
    confirmation lets anyone connecting directly spoof `X-Forwarded-For` and defeat the rate
    limiters entirely -- worse than the unset default.
  evidence: >
    Review of the `TRUSTED_PROXY_HOSTS` fix (2026-08-12) found the code itself correct but the
    risk entirely deploy-config-shaped: nothing currently forces this decision before Epic 2's
    first deploy, so the fix is formally closed in code but inert (or actively worse, if
    misconfigured) in production. `backend/.env.example`'s inline comment documents the same
    tradeoff at the point of configuration; this entry exists so it isn't only discoverable by
    someone already reading that file.

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 2.2: Document library and detail view)
  summary: >
    Extracted document text (chapter names, titles, any future preview/snippet) must render as
    plain text / React nodes only -- never `dangerouslySetInnerHTML`, and never through an
    unconfigured Markdown renderer. If a Markdown preview is ever added, it must use a
    sanitizing renderer (e.g. `react-markdown` + `rehype-sanitize`, or DOMPurify), not a raw one.
  evidence: >
    Ad-hoc security review (2026-08-12) of the existing codebase. Story 2.2's Document Detail
    renders chapter names extracted from the uploaded file itself (Story 2.3), not user-typed
    form input -- a malicious chapter heading (e.g. containing an `onerror` payload) becomes
    stored XSS the moment it's rendered as raw HTML. FR-3 explicitly lists Markdown and HTML as
    ingestible formats; most Markdown-to-HTML libraries pass raw HTML through by default unless
    configured to strip it, so an uploaded `.md` file is a direct delivery vector if any future
    preview renders extracted Markdown "as Markdown" without sanitization. No code currently
    renders raw HTML anywhere (plain JSX `{value}` auto-escapes throughout), so nothing is
    broken today -- this is a constraint for whoever builds Story 2.2/2.3, not a bug fix.
    Same risk applies to Epic 3's chat answers/citations, which also echo document-derived text.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-upload-documents-with-drag-and-drop-and-per-file-progress.md`
  summary: >
    Once the CI workflow (already tracked above) exists, add a step that runs `alembic upgrade
    head` against a real/throwaway Postgres (or an `alembic check`-style diff) rather than only
    the SQLite schema `Base.metadata.create_all` builds for tests.
  evidence: >
    Story 2.1 review (verification-gap) found every backend test builds its schema directly from
    the `Document`/`User` ORM models (`conftest.py`'s `db_session` fixture), never by running the
    actual Alembic migration files. A migration that drifts from its model (wrong nullability,
    missing FK/index, wrong column type) would pass the full test suite and only surface at a real
    deploy against Postgres. Not urgent alone, but worth folding into the CI item once that lands.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-upload-documents-with-drag-and-drop-and-per-file-progress.md`
  summary: >
    Add file-content sniffing (magic bytes, e.g. via `python-magic`) so a file's actual content is
    checked against its claimed format, not just its extension and (spoofable) Content-Type header.
  evidence: >
    Story 2.1 review (blind-hunter) noted `_ALLOWED_CONTENT_TYPES` permits `application/
    octet-stream` for every format (a deliberate, documented permissiveness for browsers/OSes with
    no `.md` mime mapping) -- so a file named `report.pdf` containing arbitrary bytes currently
    passes validation. Low priority for an MVP course project with no malware-scanning
    infrastructure, but worth knowing before Story 2.3 starts parsing uploaded content as if it
    were trustworthy PDF/Markdown/HTML.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-upload-documents-with-drag-and-drop-and-per-file-progress.md`
  summary: Sanitize/validate `filename` if it's ever used as a filesystem path (e.g. a future export or download feature) -- it's currently stored and rendered verbatim (safe today, since it's only ever rendered as escaped React text, never used as a path).
  evidence: Story 2.1 review (blind-hunter) flagged that an uploaded filename can contain path separators or `..` segments; not exploitable by any code that exists today, but worth catching before a future feature trusts it as a path.

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 2.2: Document library and detail view)
  summary: Add pagination (or a cap + "load more") to `GET /documents` and the Documents table once accounts realistically accumulate more than a page's worth of documents.
  evidence: Story 2.1 review (blind-hunter) noted the endpoint returns every document for a user with no `limit`/`offset`. Not a problem yet (fresh accounts, few documents), but epics.md explicitly leaves document count per user unbounded, so this will matter before Story 2.2's real list UI ships.

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 2.3: Parse and index documents into the vector store)
  summary: >
    Render's free tier has an ephemeral filesystem -- `fastembed`'s on-disk model-weight cache
    (`shared/embeddings/model.py`) doesn't survive a restart/redeploy/spin-down. Every time the
    instance comes back cold, the first ingestion after that pays a ~90MB model download before
    it can embed anything, so production ingestion latency will be periodically, and correctly,
    spiky -- not a bug if/when this is noticed later.
  evidence: Chosen deliberately over `sentence-transformers`/`torch` (which wouldn't fit the
    512MB free-tier instance at all) during Story 2.3's planning review. Verification for that
    story is local (persistent disk), so this won't surface in testing -- worth this recorded
    line so a later cold-start latency spike isn't debugged as a mystery.
