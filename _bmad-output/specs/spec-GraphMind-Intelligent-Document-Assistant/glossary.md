# Glossary

- **Document** — A user-uploaded file (PDF, Markdown, or HTML) ingested into GraphMind. Belongs to exactly one User.
- **Passage (Chunk)** — A segment of a Document's text, the unit stored in the vector index with its embedding and metadata (`user_id`, `document_id`, `chapter`, `chunk_index`).
- **Chapter** — A chapter/section-level metadata tag on a Passage, used to scope search within a Document. Not user-filterable in Chat in v1.
- **Knowledge Graph** — The per-User graph of Entities and Relationships extracted from all of that User's Documents, combined into one unified structure (not per-document).
- **Entity** — A node in the Knowledge Graph (e.g. a project, person, technology) extracted from Document text.
- **Relationship** — A typed edge between two Entities in the Knowledge Graph (e.g. "uses", "works on").
- **Citation** — A structured reference from a generated answer back to the specific Passage(s) that support it.
- **Refusal** — GraphMind's explicit "I don't know" response, returned when retrieval finds no adequate supporting evidence for a question.
- **User** — An authenticated account. All Documents, the Knowledge Graph, and query history belong to exactly one User (tenancy boundary).
- **Query History** — The saved record of a User's past questions and answers, including which Documents were in scope and a snapshot of citations at the time asked. Deferred to v2, not built in v1.
- **Evaluation Set** — A fixed set of question/expected-answer pairs used to measure answer accuracy and refusal correctness.
