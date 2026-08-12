"""Documented data shapes for the Weaviate and Neo4j stores (Story 1.5).

This module is **documentation only** -- there is no real Weaviate or
Neo4j client here. Epic 2 (ingestion) and Epic 3 (chat retrieval) build
the actual client code against `shared/data_access/` later; this file
exists now so those epics, and the knowledge-graph work in Epic 4, agree
on one contract up front instead of drifting into incompatible shapes.

Per architecture decision AD-2, `shared/data_access/` is the sole path to
Weaviate, Neo4j, and Postgres -- no module's `repository.py` may open its
own client/connection. That's what makes the tenancy rule below
structural rather than a matter of every call site remembering it. The
Postgres-side equivalent is `tenancy.py`'s `user_scoped_select` helper.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WeaviatePassage:
    """One chunk of a document's extracted text, as stored in Weaviate.

    Flat, no nested metadata -- every field is a top-level scalar so
    filtering (especially `user_id`) never has to reach into a nested
    object property.

    Fields:
        chunk_id: Unique id for this passage (primary key within the class).
        document_id: The parent document this chunk was extracted from.
        user_id: Owning account. Required on every write and every query
            filter -- see the NL-to-Cypher rule below for the equivalent
            Neo4j-side guarantee.
        chapter: Section/chapter label the chunk falls under, for citation
            display (e.g. "Chapter 3").
        chunk_index: 0-based position of this chunk within its document,
            for stable ordering and citation back-references.
        text: The chunk's raw extracted text, the unit embedded and
            retrieved for grounded chat answers.
        embedding: The vector embedding of `text`, used for similarity
            search at query time.
    """

    chunk_id: str
    document_id: str
    user_id: str
    chapter: str
    chunk_index: int
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class Neo4jEntity:
    """One knowledge-graph entity node, as stored in Neo4j.

    Fields:
        name: The entity's display name (e.g. "Marie Curie").
        type: The entity's category/label (e.g. "Person", "Organization").
        user_id: Owning account -- required on every write and every query
            filter, the same tenancy guarantee `WeaviatePassage.user_id`
            enforces above. Structural, not just documented in prose: a
            future Epic 2/3 write path that omits this field is wrong by
            construction, not just by convention.

    Every entity and relationship belongs to exactly one user's graph;
    node/relationship writes must carry `user_id` (as a property or via a
    per-user graph/database partition -- Epic 3/4's job to decide which).
    """

    name: str
    type: str
    user_id: str


@dataclass(frozen=True)
class Neo4jRelationship:
    """One typed edge between two entities, as stored in Neo4j.

    Relationships are typed (e.g. `(:Entity)-[:WORKED_AT]->(:Entity)`), not
    a single generic "RELATED_TO" edge -- the relationship type itself
    carries the semantic meaning Epic 4's graph view renders.

    Fields:
        source_entity_name: `name` of the relationship's source entity.
        target_entity_name: `name` of the relationship's target entity.
        relationship_type: The edge's type/label (e.g. "WORKED_AT"),
            SCREAMING_SNAKE_CASE per Neo4j convention.
        user_id: Owning account -- same tenancy requirement as
            `Neo4jEntity.user_id` above; a relationship can't outlive or
            cross the per-user boundary its two entities belong to.
    """

    source_entity_name: str
    target_entity_name: str
    relationship_type: str
    user_id: str


# ---------------------------------------------------------------------------
# Tenancy rule (forward-looking -- the *pattern* is proven now, via
# test_tenancy.py and structurally by every route depending on
# `get_current_user`; test_tenancy.py itself only exercises the
# Postgres-backed `/auth/me`, since no Weaviate/Neo4j client code exists
# yet. Epic 2/3 must extend the same pattern to real Weaviate/Neo4j calls,
# not re-derive it):
#
# Any future NL-to-Cypher query (Epic 3's chat retrieval translating a
# natural-language question into a Cypher query against Neo4j) MUST inject
# `user_id` server-side into the generated query -- resolved from
# `get_current_user`'s JWT-derived identity, never from client input (a
# request body field, query param, or anything else the caller sends).
# The same rule applies to every Weaviate query: the `user_id` filter is
# added by the server, not accepted from the request.
#
# This is the same guarantee `get_current_user` (backend/app/auth/
# dependencies.py) already provides for Postgres-backed routes like
# `/auth/me` -- this module documents that it must extend, unmodified in
# spirit, to Weaviate and Neo4j once Epic 2/3 add real queries against
# them.
# ---------------------------------------------------------------------------
