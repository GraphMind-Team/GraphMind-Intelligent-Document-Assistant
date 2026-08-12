- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-running-project-skeleton.md`
  summary: Add a CI workflow (`.github/workflows/`) running backend lint/tests and frontend lint/build on push/PR.
  evidence: Story 1.1 review (blind-hunter) found no CI configuration exists; not required to prove the skeleton runs locally, but the project has no automated gate before merge going forward.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-running-project-skeleton.md`
  summary: Add a fetch timeout / abort signal to `HealthPage.jsx` so a hung backend request doesn't leave the UI stuck on "loading" forever.
  evidence: Story 1.1 review (edge-case-hunter) found no timeout on the health-check fetch; low likelihood on localhost, real gap once deployed to Render's free tier with cold starts.
