# Web Verification Review — ARCHITECTURE-SPINE.md

Date: 2026-08-11
Scope: Stack table versions + free-tier facts (AD-7, AD-8, Deferred section)

## Verdict

**CONDITIONAL PASS.** Most claims check out and the technologies are real and fit their stated roles, but one claim (Weaviate 14-day sandbox expiry) is now **stale/superseded** by a real June 2026 change, one version claim (weaviate-client 4.22.0) could not be confirmed and conflicts with search results, and two version pins (FastAPI 0.139.x, Vite 8.0.x) are already behind current releases — none of these were confirmed to have actually been web-researched at authoring time versus asserted.

## Findings

1. **[HIGH] Weaviate Cloud "14-day sandbox expiry" is outdated as of June 2026.** Weaviate announced on 2026-06-17 that Weaviate Cloud's managed free tier is now free indefinitely ("no time expiration, no credit card"), replacing the old time-limited sandbox model. The spine's AD-7/Deferred section treats the 14-day auto-expiry as a live, must-work-around constraint (driving a "recreate and re-ingest" mitigation plan) — this planning burden may now be unnecessary, and the "verified current as of Aug 2026" label attached nearby is not credible if this predates it by two months.

2. **[MEDIUM] weaviate-client version 4.22.0 is unconfirmed / possibly invented.** Web search for the current weaviate-client Python package version returned 4.20.4 (pypistats) and 4.21.1 (official readthedocs), not 4.22.0. No source surfaced confirms a 4.22.0 release exists. This pin should be re-verified directly against PyPI before being treated as researched fact.

3. **[MEDIUM] FastAPI pin (0.139.x) and Vite pin (8.0.x) are both already stale.** Current latest versions found: FastAPI 0.141.1 (released 2026-07-29) and Vite 8.2.1 (released ~4 days before this search). Neither is wrong in the sense of being fictional, but pinning to an older minor version while implicitly presenting the table as current-as-of-Aug-2026 suggests the versions were not freshly checked at write time (or were checked weeks earlier and not updated).

4. **[LOW] Neo4j AuraDB Free limits are documented but internally inconsistent at the source.** Neo4j's own FAQ and product page disagree on Free-tier node/relationship caps (200K nodes/400K relationships vs. 50K/175K elsewhere on neo4j.com). The spine doesn't state specific capacity numbers so this doesn't contradict anything written, but if capacity planning depends on AuraDB Free later, the authoritative number needs to be pulled from the live Aura console, not marketing pages.

5. **[LOW] Render free-tier and Vercel Hobby facts check out.** Render: 750 free instance-hours/month, spin-down after 15 min idle (recently reduced from 30 min), confirmed via multiple 2026 sources — matches AD-7 exactly. Vercel Hobby: confirmed free, non-commercial-use plan with usage caps (100GB transfer, 1M invocations, etc.) — consistent with AD-7's framing, no contradiction found.

## Not independently re-verified in this pass

- Neon Postgres specific free-tier numbers (100 CU-hrs/mo, 0.5GB storage) — spine doesn't cite specifics, so nothing to contradict; general "Neon free tier" framing is accurate.
- neo4j Python driver version 6.2 — confirmed to exist (official docs page titled "Neo4j Python Driver 6.2"), consistent with spine.
- React 19.2.x — confirmed current (latest patch 19.2.8, no 19.3/20 yet), consistent with spine.
- Pydantic v2, Python 3.12+, JWT+bcrypt, OpenRouter — these are role/existence checks only (all still exist and fit their stated roles); no version-specific claim to verify beyond "v2" which is correct (Pydantic v2 is current major).

File: `_bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/reviews/review-web-verification.md`
