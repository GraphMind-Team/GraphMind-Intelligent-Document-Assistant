# GraphMind MVP - Brainstorm Intent

## Project Summary
GraphMind is a Knowledge Graph + RAG document Q&A assistant for Sirma. It lets a user upload documents, builds a per-user knowledge graph plus vector index over them, and answers questions grounded in that evidence. Built by 2 developers in ~20 days; scope is constrained by KISS/YAGNI.

## Core Product Insight
North star: users must never need to read the source documents by hand. They must trust an answer enough to skip reading the original documents themselves. Citations are the verification shortcut that earns this trust, not the goal in themselves. This insight is why the Must-list is shaped the way it is.

## Confirmed Architecture/Scope Decisions
- Graph is one unified graph across all of a user's uploaded documents, not per-document.
- Hybrid Neo4j graph + Weaviate vector RAG is a hard v1 requirement, not something to spike or validate away.
- v1 supported document types: PDF, Markdown, HTML.
- Deletion behavior (v1 simplified rule): deleting a document removes it from the library/vector store, but the knowledge graph itself is NOT retroactively pruned. This avoids reference-counting complexity.
- Per-user tenancy isolation is a hard requirement.

## MoSCoW Scope
| Priority | Items |
|---|---|
| Must | Upload + graph + vectors; grounded Q&A with citations; document library/status; delete (graph not pruned); per-user tenancy isolation |
| Should | Document scoping (ask across a chosen subset); content-hash dedupe; query history |
| Could | User graph edits (correct extracted entities/relationships); opt-in reasoning trace ("Explain this answer"); ingestion preview (live entity/relationship preview before first question) |
| Won't (this time) | Contradiction detection; correction-feed diagnostics; reference-counted delete; trust-display defaults (e.g. confidence badge) |

## Known Risks/Tensions
- Cross-user data leakage: risk that the LLM answers using another user's uploaded documents.
- Neo4j/Weaviate write desync: writes to the two stores can go out of sync on partial failure; mitigation direction identified is unified ingestion job status tracking both writes.
- Ingestion cost/latency spiral: risk from re-processing unchanged documents; mitigation direction identified is content-hash dedupe.
- Ungrounded answers: failure mode where the LLM answers from general world knowledge in a way indistinguishable from real grounding, rather than answering only from grounded document evidence or saying "I don't know."
- Delete-vs-graph-persistence trust tension: deleting a document does not retroactively prune the graph, which sits in tension with the core trust goal (users must be able to trust that what's answered reflects what they still have access to).
