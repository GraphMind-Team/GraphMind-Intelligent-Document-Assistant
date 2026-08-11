# Reconciliation: PRD/Addendum vs. Course Assignment Brief

**Source input:** Course assignment brief pasted earlier in the PRD-drafting conversation (Project 15, AI & Data Track, GraphMind — Intelligent Document Q&A with Knowledge Graphs).

**Note:** The ChromaDB→Weaviate correction is intentional (explicitly documented in addendum.md's Technology Stack table) and is not counted as a gap.

## Gaps Found

1. **No day-by-day delivery plan.** The brief's 20-day schedule (Day 1 scaffolding; Days 2-3 auth; Days 4-6 ingestion; Days 7-9 retrieval/citations/refusal; Days 10-11 documents page; Days 12-14 chat page; Days 15-17 knowledge graph; Days 18-19 evaluation/testing; Day 20 buffer/demo) is absent from both the PRD and the addendum — neither document contains any day-numbered timeline.
2. **Parallel evaluation-authoring instruction dropped.** The brief's note that "evaluation questions drafted in parallel from Day 6 onward" isn't captured anywhere; the addendum's Evaluation Harness FR only says the set is "authored incrementally as ingestion becomes functional," which loses the specific Day-6 trigger point.
3. **Chapter-level filtered search is not a first-class requirement.** The brief lists "Chapter-level document metadata with filtered search" as its own scope item (#8), but the PRD only implies it — Chapter appears in the glossary and the addendum's Q&A request flow ("filtered by user_id and optionally chapter"), while FR-11 (document scoping) describes only all-vs-subset document scoping, not chapter-level filtering explicitly.
4. **Team size narrowed without flagging it as a decision.** The brief specifies "Team of 2-3," but the PRD and addendum consistently write for a fixed two-person team (e.g., "written for the two-person build team," Team table with no mention of a possible third member) without noting this as a scoping choice, unlike the ChromaDB→Weaviate correction which is explicitly called out.
