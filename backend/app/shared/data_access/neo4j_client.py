"""Neo4j connection and the entity/relationship write path (Story 2.4, AD-2).

Per architecture decision AD-2, this is the sole place a Neo4j driver is
constructed and the sole place Cypher is written -- `documents/` (and any
future writer/reader, e.g. Epic 3/4's chat retrieval and graph view) calls
`write_entities_and_relationships` rather than importing `neo4j` itself.

Mirrors `shared/data_access/weaviate_client.py`'s pattern exactly, down to
the same double-checked-locking singleton shape and the same reasoning for
why it's hand-rolled rather than `@lru_cache`: `get_neo4j_driver` is built
inside Starlette's background-task threadpool, where two documents'
Graphing steps running concurrently could both miss an empty `lru_cache`
before either finishes connecting -- `lru_cache` holds no lock across the
wrapped call itself. Two live drivers here isn't just wasted memory, it's
the second one leaking, unclosed, past `close_neo4j_driver()`'s single
`close()` call at shutdown.

The driver is built on first use, not at import time, so importing this
module never opens a real network connection on its own (needed for tests,
and for `app.main` importing every route module at startup regardless of
whether Neo4j is configured).
"""

import logging
import os
import re
import threading

from neo4j import Driver, GraphDatabase

from app.shared.data_access.shapes import Neo4jEntity, Neo4jRelationship

logger = logging.getLogger(__name__)

_driver_lock = threading.Lock()
_driver_instance: Driver | None = None

# Relationship types reach this module already validated against OD-1's
# closed set by `shared/llm_client` -- but the Neo4j Python driver has no
# way to parameterize a relationship *type* (only property values), so it
# has to be interpolated into the Cypher string. This regex is the last
# line of defense against that interpolation ever becoming a Cypher
# injection point, independent of (not a re-trust of) the caller's own
# vocabulary check: only SCREAMING_SNAKE_CASE identifiers are ever allowed
# through, whether or not this module happens to agree with `llm_client`'s
# exact OD-1 list.
_SAFE_RELATIONSHIP_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def get_neo4j_driver() -> Driver:
    """The process-wide Neo4j driver singleton.

    A hand-rolled double-checked-locking singleton, not `@lru_cache` -- see
    this module's docstring and `weaviate_client.get_weaviate_client`'s
    docstring for the identical reasoning.
    """
    global _driver_instance
    if _driver_instance is None:
        with _driver_lock:
            if _driver_instance is None:  # re-check: lost the race, not the need
                uri = os.environ.get("NEO4J_URI")
                username = os.environ.get("NEO4J_USERNAME")
                password = os.environ.get("NEO4J_PASSWORD")
                if not uri or not username or not password:
                    raise RuntimeError(
                        "Missing required environment variable(s): NEO4J_URI, "
                        "NEO4J_USERNAME, NEO4J_PASSWORD. See backend/.env.example."
                    )
                _driver_instance = GraphDatabase.driver(uri, auth=(username, password))
    return _driver_instance


def ensure_ready() -> None:
    """Connects and ensures the `(name, type, user_id)` uniqueness
    constraint exists on `:Entity`, once, up front -- mirrors
    `weaviate_client.ensure_ready()`, called from `app.main`'s lifespan
    startup alongside it.

    Without this constraint, `MERGE` is only safe against a single
    writer: two background ingestion tasks racing to `MERGE` the same
    not-yet-existing entity (a real scenario -- Story 2.1's upload flow
    lets several files queue and process concurrently) can both find no
    match and both create a node, producing exactly the duplicate this
    story's "one graph node, not two" acceptance criterion promises
    against. `CREATE CONSTRAINT ... IF NOT EXISTS` is itself idempotent
    and safe to call every startup, unlike `weaviate_client`'s collection
    creation -- no client-side ready flag or lock needed here, since this
    only ever runs once per process at lifespan startup anyway.

    Raises whatever `get_neo4j_driver`/the constraint statement raise --
    same as `weaviate_client.ensure_ready`, the caller (`app.main`'s
    lifespan) decides whether a startup failure here is fatal or just
    logged. Community-tier Neo4j deployments that don't support composite
    uniqueness constraints would fail here every startup with no other
    effect -- ingestion still works, just without this extra guard against
    the concurrent-duplicate race; not assumed to always succeed.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        # `.consume()` rather than leaving the result unread: an
        # auto-commit result is lazy enough that an unconsumed failure
        # would surface at session close instead of here, which is the
        # difference between "the constraint statement failed" and a
        # confusing error from the `with` block's exit.
        session.run(
            "CREATE CONSTRAINT entity_name_type_user_unique IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE (e.name, e.type, e.user_id) IS UNIQUE"
        ).consume()


def close_neo4j_driver() -> None:
    """Closes the driver singleton, if one was ever built. Safe to call
    unconditionally (e.g. from `app.main`'s shutdown, alongside
    `close_weaviate_client()`) whether or not any document ever reached the
    Graphing step -- calling this never itself opens a connection just to
    immediately close it."""
    global _driver_instance
    with _driver_lock:
        if _driver_instance is not None:
            _driver_instance.close()
            _driver_instance = None


def write_entities_and_relationships(
    entities: list[Neo4jEntity],
    relationships: list[Neo4jRelationship],
    user_id: str,
) -> None:
    """The only function `documents/` calls to reach Neo4j (AD-2) -- no raw
    Cypher may appear anywhere in `documents/`.

    Entity merge is exact-match only (AD-4, no fuzzy/LLM-assisted merge):
    `MERGE (e:Entity {name: $name, type: $type, user_id: $user_id})` --
    "TechCorp" and "TechCorp Supplies" stay distinct nodes, and the same
    `(name, type, user_id)` triple merges into one node across documents
    (the story's "repeat entity across documents" scenario). Relationships
    are `MERGE`d the same way, between the two entities they reference,
    typed by `relationship_type`.

    `user_id` is a required, explicit parameter (not read off the first
    entity, the way `weaviate_client.write_passages` reads it off the first
    passage) -- every entity's and relationship's own `user_id` must match
    it exactly, or this raises before touching the driver at all. The
    caller (`documents/service.py`) resolves `user_id` server-side from the
    document's owner, never from client input (AD-2) -- this check is
    defense-in-depth against a future caller constructing the dataclasses
    with a mismatched value, not the primary tenancy guarantee.

    `Neo4jRelationship` (see `shapes.py`) carries entity *names*, not
    types -- the same name can legitimately belong to two different-typed
    entities (AD-4 again), so this function builds a name -> type lookup
    from `entities` (which *does* carry type) to resolve which node each
    relationship's `source`/`target` actually refers to. A relationship
    naming an entity absent from `entities` can't be resolved this way and
    is dropped with a warning -- there is no other source of truth for
    that entity's type to match against. A name that appears more than
    once in `entities` with *different* types is just as unresolvable --
    picking either type by dict-overwrite order would guess, and a wrong
    guess would matter (the relationship would `MATCH` against the wrong
    node's type and silently match zero rows) -- so an ambiguous name is
    excluded from the lookup entirely and any relationship naming it is
    dropped with the same warning as an absent one, not silently resolved
    against whichever entity happened to be seen last.

    All writes for one call happen inside a single Neo4j transaction: a
    driver/query error partway through fails (and rolls back) the whole
    write, so `documents/service.py`'s Graphing-step failure handling never
    has to reason about a half-written graph for one document.

    A no-op (never touches the driver) when both lists are empty -- "no
    notable entities" is a valid outcome (the story's I/O matrix), not
    something worth a connection for.
    """
    if not entities and not relationships:
        return

    for entity in entities:
        if entity.user_id != user_id:
            raise ValueError(
                "write_entities_and_relationships requires every entity's user_id to match "
                f"the given user_id -- got {entity.user_id!r} vs {user_id!r}."
            )
    for relationship in relationships:
        if relationship.user_id != user_id:
            raise ValueError(
                "write_entities_and_relationships requires every relationship's user_id to "
                f"match the given user_id -- got {relationship.user_id!r} vs {user_id!r}."
            )

    name_to_types: dict[str, set[str]] = {}
    for entity in entities:
        name_to_types.setdefault(entity.name, set()).add(entity.type)
    entity_type_by_name = {
        name: next(iter(types)) for name, types in name_to_types.items() if len(types) == 1
    }

    driver = get_neo4j_driver()
    with driver.session() as session:
        session.execute_write(_write_entities_and_relationships_tx, entities, relationships, entity_type_by_name, user_id)


def _write_entities_and_relationships_tx(tx, entities, relationships, entity_type_by_name, user_id) -> None:
    """Batched via `UNWIND` rather than one `tx.run` per item.

    A per-item loop is one network round-trip to Aura each: a document
    yielding 50 entities and 40 relationships would spend ~90 sequential
    round-trips (seconds of pure latency from a Render instance) on a write
    whose actual work is trivial. `UNWIND` collapses all entities into a
    single query.

    Relationships can't go in one query with the entities, because a
    relationship *type* is part of Cypher's syntax and can't be
    parameterized (only property values can) -- it has to be interpolated,
    so each distinct type needs its own statement. Grouping by type bounds
    that at one query per type actually present, and OD-1 closes the
    vocabulary at five types, so the whole write is at most six queries no
    matter how large the document is.

    Results are explicitly `.consume()`d: inside a transaction function the
    driver would otherwise buffer them, and a per-statement failure is
    clearer raised at its own statement than surfaced later at commit.
    """
    if entities:
        tx.run(
            "UNWIND $rows AS row "
            "MERGE (e:Entity {name: row.name, type: row.type, user_id: $user_id})",
            rows=[{"name": entity.name, "type": entity.type} for entity in entities],
            user_id=user_id,
        ).consume()

    # Grouped by relationship type -- the one part of the query that can't
    # be a parameter, so it's also the only thing forcing more than one
    # statement here.
    rows_by_type: dict[str, list[dict[str, str]]] = {}
    for relationship in relationships:
        source_type = entity_type_by_name.get(relationship.source_entity_name)
        target_type = entity_type_by_name.get(relationship.target_entity_name)
        if source_type is None or target_type is None:
            logger.warning(
                "Skipping relationship %r -[%s]-> %r: source or target not present in this "
                "call's entities (or its name is ambiguous -- multiple types), so its type "
                "can't be resolved for an exact-match merge.",
                relationship.source_entity_name,
                relationship.relationship_type,
                relationship.target_entity_name,
            )
            continue
        if not _SAFE_RELATIONSHIP_TYPE_RE.match(relationship.relationship_type):
            logger.warning(
                "Skipping relationship with an unsafe/non-vocabulary type %r between %r and %r.",
                relationship.relationship_type,
                relationship.source_entity_name,
                relationship.target_entity_name,
            )
            continue
        rows_by_type.setdefault(relationship.relationship_type, []).append(
            {
                "source_name": relationship.source_entity_name,
                "source_type": source_type,
                "target_name": relationship.target_entity_name,
                "target_type": target_type,
            }
        )

    for relationship_type, rows in rows_by_type.items():
        # `relationship_type` reaches interpolation only after passing
        # `_SAFE_RELATIONSHIP_TYPE_RE` above -- every other value in this
        # query is a bound parameter.
        query = (
            "UNWIND $rows AS row "
            "MATCH (a:Entity {name: row.source_name, type: row.source_type, user_id: $user_id}) "
            "MATCH (b:Entity {name: row.target_name, type: row.target_type, user_id: $user_id}) "
            f"MERGE (a)-[:{relationship_type}]->(b)"
        )
        tx.run(query, rows=rows, user_id=user_id).consume()
