---
title: 'Story 4.1: Explore the knowledge graph built from my documents'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '0c70fad'
provenance: 'authored-before-implementation'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `kg` module (`backend/app/kg/{routes,service,repository}.py`) has been a docstring-only stub since Story 1.1 — no endpoint exists, and nothing in the codebase has ever read from Neo4j (only `write_entities_and_relationships`, from Story 2.4, exists). `frontend/src/pages/GraphPage.jsx` is likewise a placeholder ("Coming in Epic 4"), and `react-force-graph@1.48.2` — a dependency pinned in the architecture spine specifically for this story — is installed but imported nowhere. A user who has uploaded documents and reached `Ready` has extracted entities and relationships sitting in their own Neo4j graph with no way to see them.

**Approach:** Add the first Neo4j read path, `get_graph_for_user`, in `shared/data_access/neo4j_client.py` (AD-2: the sole place Cypher may be written). It runs three scoped queries — a true-total count, a degree-ranked and capped entity list, and a relationship list restricted to the surviving entities — every one filtered on `user_id` server-side (AD-2's tenancy rule extended from writes to reads). `kg/service.py` calls it directly (mirroring `chat/service.py`'s own precedent of importing a `shared/data_access` function directly rather than routing everything through `repository.py`) and assembles a `GraphResponse` with a stable `f"{type}:{name}"` node id per entity (required because entity uniqueness is `(name, type, user_id)`, not `name` alone). `kg/routes.py` exposes this as `GET /kg/graph`, auth-only, no Postgres session needed. The frontend replaces `GraphPage.jsx`'s placeholder with a real fetch, and renders the result through `react-force-graph`'s `ForceGraph2D` with all pointer/drag/zoom interaction disabled — closing AC5 and AC7 by construction rather than by building and then restricting an interactive canvas — plus a new always-visible `GraphSummary` text component as the accessible equivalent to whatever the canvas shows sighted users.

## Boundaries & Constraints

**Always:**
- Every Cypher query in `get_graph_for_user` filters `{user_id: $user_id}` on every `Entity` match it touches, resolved server-side from `get_current_user`, never from client input (AC2, FR-2, AD-2) — the same AND-filter tenancy pattern `write_entities_and_relationships` and `weaviate_client.search_passages` already use.
- The `kg` module never imports `app.shared.llm_client` — graph visualization is a pure Cypher read (AC3, AD-6).
- The canvas wrapper renders at 480px height, matches the specified background/border/14px radius, and nodes render as circles sized by degree with centered white label text and the specified drop shadow (AC4, UX-DR11).
- The canvas is fully non-interactive: no drag, no click-to-query, no zoom/pan (AC5, UX-DR11). `enableNodeDrag`/`enablePointerInteraction`/`enableZoomInteraction`/`enablePanInteraction` are all `false`.
- Entity type is conveyed by something other than node color alone — a per-type badge/letter drawn on the node, redundant with `GraphSummary`'s grouped text list (AC6, UX-DR28).
- Because pointer interaction is fully disabled, nodes reveal nothing on hover — `GraphSummary` states this plainly ("read-only — hover and click are disabled") rather than leaving it ambiguous, and is itself the keyboard-reachable equivalent AC7 requires (AC7, UX-DR28).
- A user with zero graph entities sees an explicit plain-language message, not a blank 480px canvas (AC8).
- The entity list is capped at `GRAPH_NODE_LIMIT = 150`, kept by true whole-graph degree (ties broken by name, so the same 150 return on every reload) — a first read path against an otherwise-unbounded per-user graph must not risk an unreadable canvas or a slow query on a heavily-populated account. The true total is exposed (`total_node_count`) so the UI can say "showing top N of M."
- Because degree is computed across the whole graph but edges are only returned between surviving (capped) entities, a capped view can show large nodes with fewer drawn lines than their size implies. The UI states this plainly ("connections to entities outside this view aren't drawn") so it reads as a stated limitation, not a rendering bug.

**Ask First:** none outstanding. One judgment call worth a quick nod rather than a blocking question: `kg/repository.py` stays the existing stub (no Postgres access needed for this story), and `kg/service.py` imports `get_graph_for_user` directly from `shared/data_access/neo4j_client` — this mirrors `chat/service.py`'s existing precedent for the vector-store half of its own data access, not a new pattern.

**Never:**
- No click/hover-driven query, navigation, or detail expansion from a node. AC1's "interactive node-link diagram" refers to the force-directed layout itself (nodes settle into a readable arrangement), not pointer interactivity — worth stating plainly since AC1 and AC5 could otherwise read as contradictory.
- No per-document graph scoping in this story — the view always renders the user's whole (capped) graph, matching FR-12's literal text. Document-level filtering is out of v1 scope.
- No revalidation of `type`/`relationship_type` against `ENTITY_TYPES`/`RELATIONSHIP_TYPES` on the read path — every value at rest was already validated by `shared/llm_client` before `write_entities_and_relationships` wrote it (OD-1); the read path trusts the write path, same as the rest of this codebase's layering.
- No new Postgres schema, table, or column.
- No client-supplied `user_id`, `limit`, or scope parameter accepted anywhere on `GET /kg/graph` — the endpoint takes no query parameters at all in v1.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No entities yet | User has zero `:Entity` nodes (no documents, or none reached `Ready`, or none produced entities) | 200, `{"nodes": [], "edges": [], "total_node_count": 0}`; frontend shows a plain-language empty-state message instead of the canvas | N/A |
| Entities under the cap | `total_node_count <= 150` | All entities and their induced relationships returned; no "showing top N of M" note rendered | N/A |
| Entities over the cap | `total_node_count > 150` | Top 150 by degree (ties broken by name) returned; edges only among those 150; `total_node_count` carries the true total; frontend renders the "showing top N of M... connections outside this view aren't drawn" note | N/A |
| Isolated entity (no relationships) | An entity with degree 0 | Still rendered, at the minimum (52px) diameter | N/A |
| All entities have equal degree | Including the all-isolated (`degree = 0` for everyone) case | Every node rendered at the fixed 65px midpoint diameter (no ranking signal exists to normalize against) | N/A |
| Relationship type outside `RELATIONSHIP_TYPES` somehow present at rest | A stored relationship type not in the current closed vocabulary | Rendered as-is via `type(r)`; no read-side validation or rejection | N/A |
| Unauthenticated request | No/invalid bearer token | 401, before any Neo4j call | FastAPI's default `HTTPException` envelope |
| Cross-tenant attempt | N/A — no client-suppliable parameter can target another user's graph; `user_id` is always resolved server-side | Structurally impossible via this endpoint, not merely filtered after the fact | N/A |
| Neo4j connection/query failure | Driver/query raises | Unhandled exception → FastAPI's default 500 (AD-3) — no special-casing, consistent with how ingestion doesn't special-case store failures either | Default 500 |

</frozen-after-approval>

## Code Map

- `backend/app/shared/data_access/neo4j_client.py` -- edit: `get_graph_for_user`, three read tx functions, `GRAPH_NODE_LIMIT` constant
- `backend/app/kg/schemas.py` -- new: `GraphNode`, `GraphEdge`, `GraphResponse`
- `backend/app/kg/service.py` -- edit: `get_graph(current_user) -> GraphResponse`
- `backend/app/kg/routes.py` -- edit: `GET /graph`
- `backend/tests/test_neo4j_client.py` -- edit: `get_graph_for_user` coverage (empty, isolated entities, type-carrying relationships, cross-tenant scoping, capping/tie-break)
- `backend/tests/test_kg_graph_route.py` -- new: 200 shape, 401, cross-tenant isolation
- `frontend/src/api/graphClient.js` -- new: `getGraph(authFetch)`
- `frontend/src/api/graphClient.test.js` -- new
- `frontend/src/pages/GraphPage.jsx` -- rewrite: fetch/loading/error/empty-state/capped-note, renders `GraphCanvas`
- `frontend/src/pages/GraphPage.test.jsx` -- new
- `frontend/src/components/graph/GraphCanvas.jsx` -- new: `ForceGraph2D` wrapper (built directly from `force-graph` + `react-kapsule`, not `import ... from 'react-force-graph'` -- see Design Notes), all interaction disabled, custom node draw
- `frontend/src/components/graph/GraphCanvas.test.jsx` -- new (mocks `force-graph`/`react-kapsule`)
- `frontend/package.json` -- edit: `force-graph`, `react-kapsule` added as explicit direct dependencies (both already present transitively via `react-force-graph`); `react-force-graph` itself removed, not kept -- see Design Notes
- `frontend/src/components/graph/GraphSummary.jsx` -- new: always-visible accessible text list
- `frontend/src/components/graph/GraphSummary.test.jsx` -- new

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/data_access/neo4j_client.py` -- `get_graph_for_user`
- [x] `backend/app/kg/schemas.py` -- response models
- [x] `backend/app/kg/service.py` -- `get_graph`
- [x] `backend/app/kg/routes.py` -- `GET /graph`
- [x] backend tests (`test_neo4j_client.py` extended, `test_kg_graph_route.py` new); `pytest`: 232 passed
- [x] `frontend/src/api/graphClient.js`
- [x] `frontend/src/components/graph/GraphCanvas.jsx` + `GraphSummary.jsx` (built on `force-graph`/`react-kapsule` directly -- see Design Notes)
- [x] `frontend/src/pages/GraphPage.jsx` rewrite
- [x] frontend tests (`graphClient.test.js`, `GraphPage.test.jsx`, `GraphCanvas.test.jsx`, `GraphSummary.test.jsx`); `npm test`: 172 passed; lint/build clean
- [x] manual verification against the real dev servers + real Neo4j

**Acceptance Criteria:** (mirrors the story's own Gherkin in `epics.md`)
- Given I have documents that reached Ready, when I open Graph Preview, then an interactive node-link diagram renders, with entities as nodes and relationships as edges (FR-12).
- Given the graph query, when it runs, then it is a Cypher read issued through `shared/data_access/`, scoped to the `user_id` resolved server-side, and no other user's graph data is queryable or renderable from this view under any code path (FR-12, FR-2, AD-2).
- Given the `kg` module, when it serves this view, then it never calls the shared LLM wrapper, because graph visualization is a pure Cypher read (AD-6).
- Given the graph canvas, when it renders, then it uses the specified 480px height, background fill, border hairline and 14px radius, and nodes render as circles sized by entity prominence, with centered white label text and the specified soft drop shadow (UX-DR11).
- Given v1 scope, when I interact with the canvas, then the view is read-only: no click-to-query, no drag-to-rearrange, no editing (UX-DR11).
- Given entity types are distinguished on the canvas, when they render, then the distinction is not carried by node colour alone (UX-DR28).
- Given nodes reveal any detail on hover, when a keyboard user navigates the canvas, then an equivalent way to reach that detail exists, and if nodes carry no interaction at all, that is stated explicitly rather than left ambiguous (UX-DR28).
- Given I have no documents yet, or none that produced graph entities, when I open Graph Preview, then the view says so plainly rather than rendering an empty canvas with no explanation.

## Design Notes

- **Node-id scheme:** `f"{type}:{name}"`, not bare `name` — `Neo4jEntity` is only unique per `(name, type, user_id)` (the write path's own docstring: two different-typed entities can legitimately share a name), so the relationship query must return each endpoint's type, not just its name, to build correct `GraphEdge.source`/`target` values.
- **Why the read path skips `_SAFE_RELATIONSHIP_TYPE_RE`:** that regex exists solely because the write path interpolates a relationship type into `MERGE (a)-[:{type}]->(b)` Cypher *syntax* (types can't be parameterized). The read path's `type(r)` is a Cypher function returning a *value*, not syntax construction — it needs no interpolation and therefore no guard. Not an oversight.
- **Entity prominence:** backend-computed true whole-graph `degree` (count of relationships touching the entity, either direction, via `OPTIONAL MATCH` + `count(r)`), frontend-normalized via linear min-max into a 52–78px diameter range; fixed 65px when `minDegree === maxDegree` (covers both all-isolated and all-equal graphs, where no ranking signal exists).
- **Cap tie-break:** `ORDER BY degree DESC, e.name ASC` — without the name tie-break, `LIMIT $limit` is nondeterministic among equal-degree nodes (common at the boundary of a 150-of-thousands cut), which would make the same account's graph render a different node set on every reload.
- **Degree vs. drawn-edge divergence:** `degree` reflects true whole-graph connectivity; edges are only returned between the 150 surviving entities. A large node can therefore show fewer lines than its size implies — a deliberate trade-off (node size stays an honest importance signal) that the UI names explicitly rather than leaving to look like a bug.
- **`nodeCanvasObject`'s `ctx` is already in zoom/pan space** — node radius and font size must be divided by the `globalScale` parameter the callback receives, or the 52–78px on-screen spec drifts as the force layout's auto-fit zoom changes. This is `force-graph`'s own documented idiom for constant-screen-size drawing, not a novel workaround.
- **`ForceGraph2D` needs a real canvas 2D context and cannot render under jsdom** — its test mocks `force-graph`/`react-kapsule` entirely and only asserts wrapper markup/props and that the extracted `nodeCanvasObject` callback draws without throwing when invoked directly. `GraphSummary` carries all the real, RTL-testable accessible content.
- **`import { ForceGraph2D } from 'react-force-graph'` crashes the entire app on load — found live during manual verification, fixed before sign-off.** `react-force-graph@1.48.2` bundles its 2D/3D/VR/AR variants into one physical dist file sharing a single top-level module scope. The unused 3D/VR/AR code (from `3d-force-graph`/`-vr`/`-ar`) references the globals `THREE`/`AFRAME` at module top level, expecting them loaded via a `<script>` tag (both libraries' classic integration) rather than an ES import. Since nothing in this app ever loads either, and nothing here code-splits by route (`App.jsx` imports every page statically), importing `react-force-graph` at all crashed the *entire* app immediately on load, not just Graph Preview — reproduced live as a cascading chain (`ReferenceError: AFRAME is not defined`, then after stubbing that global, `ReferenceError: THREE is not defined`, then `TypeError: THREE.Vector3 is not a constructor`, then a further `TypeError` deep inside the VR bundle), confirming this is an unbounded chain of runtime assumptions, not one shallow guard worth patching around. Fixed by building `ForceGraph2D` directly from `force-graph` (the vanilla 2D engine `react-force-graph`'s own 2D variant delegates to internally) wrapped with `react-kapsule` (the same wrapper mechanism `react-force-graph` itself uses) — both already present in `node_modules` transitively via `react-force-graph`, now added as explicit direct dependencies since `GraphCanvas.jsx` imports them by name. Concrete side benefit, not just a workaround: the production bundle dropped from 2,250 KB (613 KB gzip) to 455 KB (144 KB gzip), and Vite's "chunk larger than 500 KB" build warning disappeared, since the unused three.js/A-Frame dependency tree is no longer pulled in at all.
- **`react-force-graph` deviation, made explicit (recorded after code review):** the architecture spine pins `react-force-graph` as this story's library-family choice. The first cut of this code kept it listed in `package.json` as an unimported dependency to "honor" that pin while sidestepping its broken combined entry point above — but an unimported package on disk doesn't honor a spine choice, it just misleads the next reader into thinking it's in use. `react-force-graph` has been removed from `package.json` entirely (`npm uninstall react-force-graph`); `force-graph` + `react-kapsule` are the actual, sole runtime dependency for the canvas, and this note is the deviation record the spine's pin requires when a story departs from it.
- **Node names and relationship types, added after code review — the original cut under-delivered AC1.** `drawNode` drew only the two-letter type badge (`TYPE_BADGES`), captioned by a comment claiming "the drawn node label already carries the entity's name" — false; nothing on the canvas ever drew `node.name`, and `nodeLabel={null}` disabled the hover tooltip that would have. `GraphSummary`'s list was also collapsed by default (`<details>` without `open`), so the only way to learn a single entity's name was an extra click, and `GraphEdge.type` was fetched by the backend but never rendered anywhere on the frontend. Fixed three ways: (1) `drawNode` now draws `node.name` beneath each circle, same `/globalScale` treatment as the badge/radius, so it stays constant-size on screen; (2) `GraphSummary`'s `<details>` now renders `open` by default (today's graphs are small, a handful of entities per account) while staying collapsible for a much larger future graph; (3) `GraphSummary` now renders a "Relationships" list under the entity groups, one line per edge as `<source name> <TYPE> <target name>`, resolving `GraphEdge.source`/`target` ids back to names via the same `nodes` array already passed in. No canvas-level edge-label drawing was added (`force-graph`'s `linkCanvasObject`) — with names now drawn under every node, rotated in-canvas edge labels would add clutter without adding information the text list doesn't already carry.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- 232 passed, including 8 new `get_graph_for_user` cases and 4 new `test_kg_graph_route.py` cases.
- `npm test -- --run` / `npm run lint` / `npm run build` (from `frontend/`) -- 172 passed; lint clean (only the pre-existing `only-export-components` fast-refresh warnings shared with `AuthContext.jsx`/`ThemeContext.jsx`/`ChatScopeContext.jsx`/`StatusPill.jsx`); build clean, 455 KB bundle (144 KB gzip), no chunk-size warning.

**Manual checks -- completed against the real backend/frontend dev servers, real Neo4j (account: `essinkabg@gmail.com`, which already carried `story32_verify_doc.md`'s real extracted entities from Story 3.3's own verification):**
- Opened Graph Preview -- rendered a real canvas, not the placeholder: `role="img"` wrapper with computed styles `height: 480px`, `border-radius: 14px`, border/background matching the light-mode `--border`/`--card-bg` tokens exactly (`rgb(199, 210, 230)` / `rgb(255, 255, 255)`), a real `<canvas>` element present inside it. `GraphSummary`'s "View as list" showed the real data: 8 entities across 5 types (Location, Organization, Person, Product, Project) and 6 relationships -- confirms AC1/AC4 live, not just via mocked tests.
- Confirmed entity type is distinguishable by something other than color: `GraphSummary`'s grouped-by-type list is a second, always-visible way to see type, redundant with the canvas's per-node badge (AC6).
- Dispatched real `mousedown`/`mousemove`/`mouseup`/`click` events at the canvas's center (simulating a click-and-drag) -- `window.location.href` unchanged before/after, confirming no click-to-query or drag-to-rearrange occurs (AC5/AC7).
- **Cross-tenant isolation (AC2), verified directly against real Neo4j, not via a second account** (per this project's one-QA-account convention): ran `get_graph_for_user` from a Python REPL using real `backend/.env` credentials. The real account's own `user_id` returned its true data (8 entities, 6 relationships, `total_node_count=8`); a bogus/nonexistent `user_id` (`00000000-0000-0000-0000-000000000000`) returned exactly `([], [], 0)` -- the same shape `GET /kg/graph` would serialize as the empty state.
- Grepped `backend/app/kg/` for any import of `app.shared.llm_client` -- zero matches (AC3).
- Dark-mode spot check: toggled `theme` to `dark` and reloaded -- canvas wrapper's computed `border-color`/`background-color` switched to the dark tokens exactly (`rgb(58, 65, 80)` / `rgb(38, 43, 53)`, i.e. `--border-dark`/`--card-bg-dark`), canvas still present and correctly sized. Confirms `GraphCanvas`'s hand-mirrored `PALETTE` constant (Design Notes) tracks the live theme correctly, with no stale-color flash from the timing race that constant was written to avoid.
- **One real finding from manual verification, fixed before sign-off:** `import { ForceGraph2D } from 'react-force-graph'` crashed the entire app (not just Graph Preview) on every page load -- see Design Notes for the full root-cause writeup and fix (rebuilding `ForceGraph2D` from `force-graph` + `react-kapsule` directly). Re-verified live afterward: app loads cleanly, Graph Preview renders correctly, no console errors on login/navigation.
- Not manually re-verified live: the empty-state UI copy (AC8) and the "showing top N of M" capped note -- the one QA account's real graph (8 entities) is neither empty nor over the 150-entity cap, and this project's QA convention is one standing account, no throwaways. Both covered by automated `GraphPage.test.jsx` cases instead (`shows a plain-language empty state...`, `shows the "showing top N of M" note...`).
- Cleanup: no documents were uploaded and no data was written for this story's manual verification (a pure read path, reusing the QA account's existing entities) -- nothing to remove afterward. Reset the dev browser's `theme` localStorage key back to `light` after the dark-mode check.
