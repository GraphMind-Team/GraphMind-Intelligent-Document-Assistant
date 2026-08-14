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
    instance comes back cold, the first ingestion after that pays a model download before it can
    embed anything (~0.22GB for `paraphrase-multilingual-MiniLM-L12-v2`, the model actually
    shipped -- swapped in during review from the smaller English-only `all-MiniLM-L6-v2`,
    ~0.09GB, specifically so Bulgarian documents get real embeddings), so production ingestion
    latency will be periodically, and correctly, spiky -- not a bug if/when this is noticed later.
  evidence: Chosen deliberately over `sentence-transformers`/`torch` (which wouldn't fit the
    512MB free-tier instance at all) during Story 2.3's planning review. Verification for that
    story is local (persistent disk), so this won't surface in testing -- worth this recorded
    line so a later cold-start latency spike isn't debugged as a mystery.

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 2.3: Parse and index documents into the vector store)
  summary: Author a `spec-2-3-parse-and-index-documents-into-the-vector-store.md` under `_bmad-output/implementation-artifacts/`, matching the pattern every other shipped story (1.1/1.2/1.5/2.1/2.2) has -- 2.3 was implemented directly against `epics.md`'s acceptance criteria plus `epic-2-context.md`, with no dedicated spec file of its own.
  evidence: Noted during a Story 2.3 review round; `sprint-status.yaml` and `deferred-work.md`'s own entries for 2.3 both reference `epics.md` directly rather than a spec file, unlike every neighboring story. Not a code defect -- a process/documentation gap worth closing before 2.4 sets the same precedent.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-extract-entities-into-the-unified-graph-with-compensating-ro.md`
  summary: >
    Benchmark `documents/service.py`'s `EXTRACTION_CHAR_BUDGET` (12,000 characters, ~3k tokens) against
    a real long document, and reconsider the truncation strategy if it's cutting off entities/
    relationships that matter -- today it's a straight head-of-document truncation (the first
    12,000 characters of concatenated chapter text, in parse order), so any content past that point
    is invisible to entity extraction even though it's still fully indexed (untruncated) in Weaviate.
  evidence: >
    Design Notes explicitly flag this as "not benchmarked against a real long document" -- the
    budget was picked as a conservative fit under free-tier OpenRouter context limits alongside the
    extraction prompt itself, not derived from measuring extraction quality on an actual large
    upload. A document whose most graph-relevant content sits late (e.g. an appendix, a contacts
    list, a conclusion) would silently lose that content to extraction with no error or warning.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-extract-entities-into-the-unified-graph-with-compensating-ro.md`
  summary: >
    `neo4j_client.py`'s AD-4 exact-match/near-match `MERGE` claims (`test_neo4j_client.py`) are
    verified against a fake transaction recorder that asserts the Cypher/params sent, not against a
    real or embedded Neo4j engine actually executing a `MERGE`. A regression that changed `MERGE` to
    `CREATE` would only be caught by one general test asserting `"MERGE (e:Entity" in query`, not by
    the exact-match/near-match tests themselves -- they'd still pass. No integration test against a
    real Neo4j instance exists anywhere in the suite (CI has no Neo4j service).
  evidence: >
    Raised independently by two of three adversarial review passes on Story 2.4. Mitigated, not
    eliminated: `ensure_ready()` now creates a `(name, type, user_id)` uniqueness constraint at
    startup (best-effort, logged not fatal) specifically so a real Neo4j instance enforces the
    "one node, not two" guarantee even if application-level `MERGE` logic regresses.
    Update: both the constraint creation and the merge semantics were manually verified once
    against live Neo4j Aura at the end of Story 2.4 (repeated entity across two writes -> one node;
    "TechCorp" vs "TechCorp Supplies" -> distinct nodes; repeated relationship -> one edge). That
    closes the "never actually run" concern, but it was a one-off manual check, not a repeatable
    test -- a regression would still ship silently.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-extract-entities-into-the-unified-graph-with-compensating-ro.md`
  summary: >
    `llm_client.DEFAULT_MODEL` pins a free-tier OpenRouter slug, and free slugs get withdrawn
    without notice -- the story's original default (`meta-llama/llama-3.3-70b-instruct:free`) was
    already dead by the first live upload, returning 404 "unavailable for free". Worth either a
    startup health-check that surfaces a dead model as a visible warning rather than as every
    document failing at the Graphing step, or a documented fallback chain across two or three free
    slugs.
  evidence: >
    Every test in `test_entity_extraction.py` mocks `httpx.post`, so no automated check can ever
    catch a withdrawn slug -- the story shipped with a default that could not work, and only a real
    upload revealed it. `OPENROUTER_MODEL` is an env override (documented in `.env.example`) so the
    immediate fix is configuration, but the failure mode is loud and late rather than early.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-extract-entities-into-the-unified-graph-with-compensating-ro.md`
  summary: >
    Run one real end-to-end ingestion against the live OpenRouter API before relying on Story 2.4 in
    production. The default model is a `:free` tier (`meta-llama/llama-3.3-70b-instruct:free`) and
    the request sends `response_format: {"type": "json_object"}`, which not every free model on
    OpenRouter honours -- a provider that rejects the parameter returns a 4xx, which is
    (correctly) non-retryable and would mark every document `Failed`. `OPENROUTER_MODEL` is already
    an env override, so the fix if this happens is configuration, not code.
  evidence: >
    No test in the suite makes a live OpenRouter call (all mock `httpx.post`), so the request shape
    is verified only against the code's own assumptions about what the provider accepts. The spec's
    own "Manual checks" section calls for exactly this run; recorded here so it isn't lost if the
    story merges before someone performs it.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-extract-entities-into-the-unified-graph-with-compensating-ro.md`
  summary: >
    `DocumentsPage`'s ingestion-status polling is a fixed 4s interval capped at 45 attempts (3
    minutes). It is a stopgap sized against a guess at the slow path, not a measurement: a document
    that legitimately takes longer than 3 minutes stops updating and needs a manual reload, and
    every polling client re-fetches the whole document list each tick. Worth replacing with
    server-sent events / websockets, or at minimum an exponential-backoff interval, once Epic 3's
    chat work establishes whether this app wants a push channel at all.
  evidence: >
    Raised during Story 2.4's review, when polling `Uploaded` only was found to stop the loop before
    a document ever reached `Ready`. Widening the status set fixed the correctness bug; the
    poll-based mechanism itself remains the crude part, and the 3-minute ceiling is an assumption
    about ingestion duration that no benchmark backs (see also the `EXTRACTION_CHAR_BUDGET` entry).

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 3.1: Ask a question and receive a grounded, cited answer)
  summary: >
    AC14 (NFR-1, p95 chat-answer latency under 8 seconds) is knowingly not met by the shipped
    configuration. `shared/llm_client`'s `_CHAT_TIMEOUT_SECONDS`/`_CHAT_MAX_ATTEMPTS` comment
    documents a measured ~32s real call against the free-tier default model, with a ~120s worst
    case across both attempts (45s + up to 30s of a 429's own `Retry-After` + 45s). No test
    asserts NFR-1, so nothing in CI or the review loop will ever flag this as a regression --
    only this line and the code comment record that it's a known, accepted gap rather than an
    oversight. `OPENROUTER_CHAT_MODEL` (backend/.env.example) is the intended fix once a faster
    free/paid model is chosen; unset, it falls back to the same slow default.
  evidence: >
    Story 3.1 review found the deviation was previously only discoverable by reading
    `shared/llm_client/__init__.py`'s inline comments -- neither `deferred-work.md` nor
    `sprint-status.yaml` carried any record of it, unlike every other knowingly-accepted gap in
    this project (see e.g. the `TRUSTED_PROXY_HOSTS` and `EXTRACTION_CHAR_BUDGET` entries above).

- source_spec: `_bmad-output/planning-artifacts/epics.md` (Story 3.1: Ask a question and receive a grounded, cited answer)
  resolved: 2026-08-14 -- `spec-3-1-ask-a-question-and-receive-a-grounded-cited-answer.md` written.
  summary: >
    Author a `spec-3-1-ask-a-question-and-receive-a-grounded-cited-answer.md` under
    `_bmad-output/implementation-artifacts/`, matching the pattern every other shipped story
    (1.1/1.2/1.5/2.1/2.2/2.4) has -- 3.1 was implemented directly against `epics.md`'s
    acceptance criteria, with no dedicated spec file of its own.
  evidence: >
    Same gap as the still-open Story 2.3 entry above, which explicitly warned this would
    recur ("worth closing before 2.4 sets the same precedent") -- 2.4 did get a spec file, but
    3.1 didn't. Concretely cost something this time: without a Boundaries section recording
    UX-DR21's `#4A7FE0`/`#D1EEFE` pair as a documented, human-accepted deviation, Story 3.1's
    review re-tuned the citation-chip contrast without first checking whether it was an
    oversight or a recorded decision (it was the latter -- closing it was still correct, but the
    docs it contradicted had to be reconciled after the fact instead of the spec surfacing the
    tension up front).
  resolution_note: >
    Kept rather than deleted, with a `resolved:` line added, because the lesson is the point --
    this is the second occurrence of the same gap and the Story 2.3 entry above is STILL open.
    The new spec is explicit that it was reconstructed after implementation (see its provenance
    block): its Boundaries describe what 3.1 turned out to be bound by, not decisions a human
    approved in advance, so no future story should read those lines as carrying the authority a
    genuinely pre-approved Boundaries section does. A retro-spec presenting itself as frozen
    would invite the mirror image of the UX-DR21 error -- a later story declining to revisit a
    line that was never actually negotiated.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-failed-ingestion-surfaced-with-a-readable-reason.md`
  summary: >
    `Document.failed_reason` is never cleared back to `None` on a subsequent successful ingestion,
    so if a document that previously failed is ever re-ingested and reaches `Ready`, it would keep
    displaying its old failure text alongside a `Ready` status.
  evidence: >
    Story 2.5 review (blind-hunter) raised this. Currently unreachable: no retry endpoint exists
    anywhere in `routes.py` (confirmed by investigation during this story's planning), so
    `ingest_document` only ever runs once per document today. Revisit when a retry story is built —
    that story's spec should clear `failed_reason` in the same commit that sets `status = "Ready"`.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-failed-ingestion-surfaced-with-a-readable-reason.md`
  summary: >
    `Document.failed_reason` truncates the underlying exception's `str()` to 300 characters but does
    not scrub its content — a driver/provider error that happens to embed a connection string,
    internal hostname, or other sensitive detail would be truncated, not redacted, and could reach
    the API response and the UI.
  evidence: >
    Story 2.5 review (blind-hunter) raised this. No known instance today (Weaviate/Neo4j/OpenRouter
    client errors observed in this codebase's tests are plain messages like "Weaviate is
    unreachable"), and building a reliable redaction pass (allow-listing vs. pattern-matching
    secrets in arbitrary third-party exception text) is real scope, not a one-line fix — worth a
    deliberate design pass rather than folding into this story.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-failed-ingestion-surfaced-with-a-readable-reason.md`
  summary: >
    `ingest_document`'s recovery path (`db.rollback(); document.status = "Failed";
    document.failed_reason = ...; db.commit()`) is itself wrapped in a bare `except Exception:` that
    logs and swallows a failure there, with no test pinning what state the row is left in if that
    second commit fails (e.g. a DB outage during the very commit meant to record the first failure).
  evidence: >
    Story 2.5 review (blind-hunter) raised this. Pre-existing pattern from Story 2.3/2.4 — this
    story only added one more field write inside that same already-swallowed block, so the gap
    predates this change and isn't specific to `failed_reason`.
