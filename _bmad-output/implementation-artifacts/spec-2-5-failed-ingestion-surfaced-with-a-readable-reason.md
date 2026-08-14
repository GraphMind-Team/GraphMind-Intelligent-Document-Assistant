---
title: 'Story 2.5: Failed ingestion surfaced with a readable reason'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'ea1be89d085bac13c10880bd671c548af5faab82'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `ingest_document` (Stories 2.3/2.4) already marks a document `Failed` on any pipeline exception, but only logs the underlying error — nothing is persisted or shown to the user, so a Failed document gives no clue why. `Document.docstring` already anticipates this ("failed_reason in 2.5") but the column doesn't exist yet.

**Approach:** Add a nullable `Document.failed_reason` column, populate it in the same commit that sets `status = "Failed"` with a short, human-readable, stage-aware message (parsing/indexing/extraction/graph-write), and render it on Document Detail only — never inline in the Documents table row (human decision).

## Boundaries & Constraints

**Always:**
- `failed_reason` is set in the exact same `db.commit()` that sets `status = "Failed"` (service.py line ~360) — never a separate write, so the two fields can never disagree about whether a reason exists.
- The reason is stage-aware, not a raw exception dump: track which stage (`parsing`, `indexing`, `extraction`, `graph write`) was in flight when the exception was caught, and prefix a short human label to `str(exc)`, truncated to 300 chars — long tracebacks or provider payloads never land in the DB or UI.
- `except Exception:` (line 336) becomes `except Exception as exc:` so the exception is available to build the reason; existing `logger.exception(...)` call is unchanged.
- `failed_reason` is only ever set on the `Failed` path — every existing success-path field (`chapter_breakdown`, `status = "Ready"`) is untouched by this story.
- `DocumentResponse.failed_reason: str | None = None`, populated straight from the model.
- Document Detail renders the reason only when `status === 'Failed'`; every other status's existing rendering (including the "Pending" convention for Ready-only fields) is unchanged.
- New Alembic migration chains off `c7d2a4f8e6b1` (the `chapter_breakdown` migration), adding one nullable `String` column — mirrors that migration's shape exactly.

**Ask First:** none.

**Never:**
- No retry endpoint or retry-lock changes — story 2.3/2.4 already documented "retry only accepted from Failed" as a *future* guard; no retry endpoint exists yet anywhere in `routes.py`, and this story does not add one.
- No inline placement in the Documents table row — human-decided Detail-only; do not add a subtext line under the row's status pill.
- No new status-pill tint/token work — Story 1.2's danger pair (`StatusPill.jsx`) already covers `Failed` and needs no changes.
- No structured/typed error taxonomy (error codes, i18n keys) — a plain string column and a plain string prop, matching this project's existing "reason goes to the logger" -> "reason goes to a text field" precedent from 2.3/2.4.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parse failure | Corrupt/unparseable file at the parsing stage | `status = "Failed"`, `failed_reason` starts with a parsing-stage label + truncated `str(exc)` | N/A |
| Weaviate write failure | `write_passages` raises during indexing | `status = "Failed"`, `failed_reason` starts with an indexing-stage label | N/A |
| Extraction failure | `extract_entities_and_relationships` raises `ExtractionError` after retries | `status = "Failed"`, `failed_reason` starts with an extraction-stage label | N/A |
| Neo4j write failure | `write_entities_and_relationships` raises | `status = "Failed"`, `failed_reason` starts with a graph-write-stage label | N/A |
| Very long underlying error message | Exception's `str()` exceeds 300 chars | `failed_reason` is truncated to 300 chars, never stored/rendered raw | N/A |
| Failed document in the list | `GET /documents` | Row still present (unchanged from 2.3), status pill uses existing danger tint, no reason text in the row | N/A |
| Failed document detail view | `GET /documents/{id}`, `status == "Failed"` | Reason text rendered in Document Detail; every Ready-only field (`chapter_breakdown` etc.) still shows "Pending"/unavailable, never fabricated | N/A |
| Non-Failed document detail view | `status` in `Uploaded/Extracting/Graphing/Ready` | No reason block rendered at all | N/A |

</frozen-after-approval>

## Code Map

- `backend/alembic/versions/` -- new: migration chained off `c7d2a4f8e6b1`, adds nullable `documents.failed_reason` (String)
- `backend/app/shared/models.py` -- edit: `Document.failed_reason: Mapped[str | None] = mapped_column(String, nullable=True)` (mirrors line 77's `chapter_breakdown` column style)
- `backend/app/documents/schemas.py` -- edit: `DocumentResponse.failed_reason: str | None = None`
- `backend/app/documents/service.py` -- edit: `ingest_document` (lines 251-376) — track current stage before each risky call, catch the exception (`except Exception as exc:`, line 336), derive `reason` from stage label + truncated `str(exc)`, set `document.failed_reason = reason` in the same commit as `document.status = "Failed"` (line 358-361)
- `frontend/src/pages/DocumentDetailPage.jsx` -- edit: new section rendered when `doc.status === 'Failed'`, showing `doc.failed_reason`, placed after the existing chapter-breakdown section (~line 146)
- `backend/tests/test_documents_parse_and_index.py` -- edit: extend `test_ingest_corrupt_file_marks_failed_instead_of_stuck` (258) and `test_ingest_weaviate_write_failure_marks_failed` (282) with `failed_reason` assertions
- `backend/tests/test_documents_ingest_graphing.py` -- edit: extend the three existing Failed-path tests (232, 254, 273) with `failed_reason` assertions, reusing the existing `_stub_pipeline`/`_raise` fixtures
- `backend/tests/test_documents_detail.py` -- edit: add a Failed-status case asserting `failed_reason` appears in the response
- `frontend/src/pages/DocumentDetailPage.test.jsx` -- edit: add a Failed-status case rendering `failed_reason`, and a non-Failed case asserting no reason block renders
- `frontend/src/pages/DocumentsPage.test.jsx` -- edit: matrix audit addition — Failed row never renders `failed_reason` inline

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/models.py` + new Alembic migration -- `failed_reason` nullable String column on `documents`, chained off `c7d2a4f8e6b1`
- [x] `backend/app/documents/schemas.py` -- `DocumentResponse.failed_reason`
- [x] `backend/app/documents/service.py` -- stage tracking + reason derivation + `document.failed_reason` set alongside `status = "Failed"` -- the story's core AC
- [x] `frontend/src/pages/DocumentDetailPage.jsx` -- Failed-status reason block
- [x] `backend/tests/test_documents_parse_and_index.py` + `backend/tests/test_documents_ingest_graphing.py` -- `failed_reason` assertions on all four existing failure-path tests, plus a truncation-boundary test
- [x] `backend/tests/test_documents_detail.py` -- Failed-status API response includes `failed_reason`
- [x] `frontend/src/pages/DocumentDetailPage.test.jsx` -- Failed-status reason rendering + non-Failed absence case
- [x] `frontend/src/pages/DocumentsPage.test.jsx` -- Failed row never renders the reason inline (matrix audit addition)

**Acceptance Criteria:**
- Given a document whose ingestion fails at any stage (parsing, indexing, extraction, graph write), when the failure is handled, then `status = "Failed"` and `failed_reason` is set in the same commit, and the document is never silently dropped from the list.
- Given a Failed document, when the Documents list renders, then its row shows the existing danger status pill and no reason text (Detail-only, human-decided).
- Given a Failed document, when Document Detail loads, then a human-readable reason is shown.
- Given a non-Failed document, when Document Detail loads, then no Failed-reason block is rendered.
- Given an underlying exception message longer than 300 chars, when `failed_reason` is derived, then it is truncated, never stored or rendered raw.

## Design Notes

Stage labels, in pipeline order: `"Could not read this document"` (parsing), `"Could not index this document's content"` (indexing/Weaviate), `"Could not extract entities from this document"` (extraction), `"Could not save extracted entities to the graph"` (graph write/Neo4j). Reason format: `f"{stage_label}: {str(exc)[:300]}"`. A local `stage` variable, reassigned immediately before each risky call (mirroring how `document.status` is already reassigned inline through the same function), is simpler than restructuring into per-stage `try/except` blocks and keeps the single outer `except` AD-1's rollback logic already depends on.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including extended failure-path assertions
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: clean, including new Detail test cases

**Manual checks (if no CLI):**
- Force a failure (e.g. temporarily break `NEO4J_URI`) on a real upload, confirm the document reaches `Failed` in the Documents list with the danger pill and no inline reason, then open Document Detail and confirm a readable reason is shown.

## Suggested Review Order

**Reason derivation (backend core)**

- Stage-aware labels + truncation, joined into one short string — the mechanism the whole story hangs off.
  [`service.py:83-93`](../../backend/app/documents/service.py#L83)

- `stage` reassigned right before each risky call, moved ahead of the Graphing-status commit during review so a commit failure there isn't mislabeled as an indexing failure.
  [`service.py:291`](../../backend/app/documents/service.py#L291), [`service.py:307`](../../backend/app/documents/service.py#L307), [`service.py:338`](../../backend/app/documents/service.py#L338), [`service.py:358`](../../backend/app/documents/service.py#L358)

- Exception bound and `failed_reason` set in the exact same commit as `status = "Failed"` — the story's core invariant.
  [`service.py:370`](../../backend/app/documents/service.py#L370), [`service.py:398`](../../backend/app/documents/service.py#L398)

**Data model & API contract**

- New nullable column, docstring already anticipated it from Story 2.4.
  [`models.py:85`](../../backend/app/shared/models.py#L85)

- Migration chained off the `chapter_breakdown` migration, same shape.
  [`d4e9b1f3a7c2_add_failed_reason_to_documents.py`](../../backend/alembic/versions/d4e9b1f3a7c2_add_failed_reason_to_documents.py#L1)

- Response field, populated straight from the model.
  [`schemas.py:32`](../../backend/app/documents/schemas.py#L32)

**Frontend rendering (Detail-only, human decision)**

- Reason block gated on `status === 'Failed'`, falls back to fixed text when null, wraps long text.
  [`DocumentDetailPage.jsx:153`](../../frontend/src/pages/DocumentDetailPage.jsx#L153)

**Tests**

- Four failure-path tests pin the stage label + underlying message per stage.
  [`test_documents_parse_and_index.py:258`](../../backend/tests/test_documents_parse_and_index.py#L258), [`test_documents_parse_and_index.py:284`](../../backend/tests/test_documents_parse_and_index.py#L284), [`test_documents_ingest_graphing.py:232`](../../backend/tests/test_documents_ingest_graphing.py#L232), [`test_documents_ingest_graphing.py:257`](../../backend/tests/test_documents_ingest_graphing.py#L257)

- Truncation-boundary test, added during matrix audit.
  [`test_documents_parse_and_index.py:308`](../../backend/tests/test_documents_parse_and_index.py#L308)

- API round-trip for a Failed document.
  [`test_documents_detail.py:183`](../../backend/tests/test_documents_detail.py#L183)

- Frontend: reason renders, null falls back, non-Failed renders nothing, and the row itself never shows it.
  [`DocumentDetailPage.test.jsx:124`](../../frontend/src/pages/DocumentDetailPage.test.jsx#L124), [`DocumentDetailPage.test.jsx:154`](../../frontend/src/pages/DocumentDetailPage.test.jsx#L154), [`DocumentsPage.test.jsx:78`](../../frontend/src/pages/DocumentsPage.test.jsx#L78)
