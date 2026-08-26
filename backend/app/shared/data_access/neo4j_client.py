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
import re
import threading

from neo4j import Driver, GraphDatabase

from app.shared.data_access.shapes import Neo4jEntity, Neo4jRelationship
from app.shared.env import env_str

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

# Story 4.1's read path caps how many entities one Graph Preview response
# renders. A first read against an otherwise-unbounded per-user graph --
# a handful of documents can plausibly extract thousands of entities --
# needs a bound both for query cost and for the canvas staying legible;
# 150 is a defensive ceiling, not a measured value.
GRAPH_NODE_LIMIT = 150

# The node cap bounds *entities* quadratically, not edges: up to
# GRAPH_NODE_LIMIT^2 directed pairs among 150 survivors, times up to five
# relationship types per pair (OD-1's closed vocabulary) if the same two
# entities are related more than one way -- tens of thousands of rows in
# the worst case, with nothing else bounding the query or the response
# payload. A defensive ceiling, not a measured value, mirroring
# GRAPH_NODE_LIMIT's own reasoning.
GRAPH_EDGE_LIMIT = 1000


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
                uri = env_str("NEO4J_URI")
                username = env_str("NEO4J_USERNAME")
                password = env_str("NEO4J_PASSWORD")
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
    document_id: str,
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

    `document_id` (Story 2.8, OD-4) is required and stamped onto every
    entity's and relationship's `source_document_ids` list property --
    appended only if not already present (`coalesce(existing, []) + id`
    guarded by a membership check), so calling this twice for the same
    document (Story 2.6's reingest-on-Failed path) never produces a
    duplicate entry. This is what makes `prune_document_from_graph` able to
    reference-count: an entity/relationship is deleted only once every
    document that ever contributed it has removed its id from this list.

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
        session.execute_write(
            _write_entities_and_relationships_tx,
            entities,
            relationships,
            entity_type_by_name,
            user_id,
            document_id,
        )


# Shared between the entity and relationship `MERGE` statements below --
# appends `$document_id` to `source_document_ids` only if it isn't already
# there, so writing the same document's entities twice (Story 2.6's
# reingest-on-Failed path) never produces a duplicate list entry.
_APPEND_SOURCE_DOCUMENT_ID = (
    "coalesce({var}.source_document_ids, []) + "
    "CASE WHEN $document_id IN coalesce({var}.source_document_ids, []) THEN [] ELSE [$document_id] END"
)


def _write_entities_and_relationships_tx(
    tx, entities, relationships, entity_type_by_name, user_id, document_id
) -> None:
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
            "MERGE (e:Entity {name: row.name, type: row.type, user_id: $user_id}) "
            f"SET e.source_document_ids = {_APPEND_SOURCE_DOCUMENT_ID.format(var='e')}",
            rows=[{"name": entity.name, "type": entity.type} for entity in entities],
            user_id=user_id,
            document_id=document_id,
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
            f"MERGE (a)-[r:{relationship_type}]->(b) "
            f"SET r.source_document_ids = {_APPEND_SOURCE_DOCUMENT_ID.format(var='r')}"
        )
        tx.run(query, rows=rows, user_id=user_id, document_id=document_id).consume()


def prune_document_from_graph(document_id: str, user_id: str) -> None:
    """Removes `document_id`'s attribution from every entity/relationship it
    contributed, deleting the node/relationship itself once no surviving
    document still supports it (Story 2.8, OD-4's reference-counted
    pruning). The only new *request-path* Neo4j entry point this story
    adds -- called from `documents/service.py::delete_document` after the
    existing Weaviate passage delete and before the Postgres row delete.
    (`wipe_all_entities_and_relationships` below is also new, but is never
    called from request-serving code -- see its own docstring.)

    Relationships are pruned first, then entities, inside a single
    transaction -- matching the order `write_entities_and_relationships`
    writes them in (a relationship is only ever written alongside both its
    endpoint entities in the same call, per that function's own name
    resolution), so a relationship never outlives an entity it depends on
    having survived, nor is an entity ever deleted while a still-alive
    relationship still names it. `DETACH DELETE` on the entity pass is
    what would clean up any such relationship anyway, but pruning
    relationships first keeps the two passes independently correct rather
    than relying on that as a safety net.

    A legacy entity/relationship with no `source_document_ids` at all
    (written before this story's rebuild) is treated as already-empty by
    `coalesce(..., [])` -- `document_id` is never found in an empty list,
    so it's never matched and never touched, exactly the "untracked, left
    alone" behavior the story's I/O matrix requires for that case.

    Idempotent: pruning the same `document_id` twice (or pruning a
    document that contributed nothing) matches zero rows on the second
    call and deletes nothing further.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.execute_write(_prune_document_from_graph_tx, document_id, user_id)


def _prune_document_from_graph_tx(tx, document_id, user_id) -> None:
    tx.run(
        "MATCH (:Entity {user_id: $user_id})-[r]->(:Entity {user_id: $user_id}) "
        "WHERE $document_id IN coalesce(r.source_document_ids, []) "
        "SET r.source_document_ids = [id IN r.source_document_ids WHERE id <> $document_id] "
        "WITH r WHERE size(r.source_document_ids) = 0 "
        "DELETE r",
        user_id=user_id,
        document_id=document_id,
    ).consume()

    tx.run(
        "MATCH (e:Entity {user_id: $user_id}) "
        "WHERE $document_id IN coalesce(e.source_document_ids, []) "
        "SET e.source_document_ids = [id IN e.source_document_ids WHERE id <> $document_id] "
        "WITH e WHERE size(e.source_document_ids) = 0 "
        "DETACH DELETE e",
        user_id=user_id,
        document_id=document_id,
    ).consume()


def delete_entities_for_user(user_id: str) -> None:
    """Deletes every `:Entity` node owned by `user_id` (and, via
    `DETACH DELETE`, every relationship touching one) -- the user-scoped
    sibling to `wipe_all_entities_and_relationships`'s global wipe, added
    for Story 5.3's account-deletion cascade.

    Unlike `wipe_all_entities_and_relationships`, this *is* safe to call
    from request-serving code: scoped to one user's own data, the same
    tenancy boundary every other function in this module
    (`write_entities_and_relationships`, `prune_document_from_graph`,
    `get_graph_for_user`) already enforces on every `Entity` match.

    Idempotent: a user with zero entities (or a retry after a partial
    earlier failure elsewhere in the same account-deletion cascade)
    matches zero rows and deletes nothing further.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.execute_write(_delete_entities_for_user_tx, user_id)


def _delete_entities_for_user_tx(tx, user_id) -> None:
    tx.run(
        "MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e",
        user_id=user_id,
    ).consume()


def wipe_all_entities_and_relationships() -> None:
    """Deletes every `:Entity` node (and, via `DETACH DELETE`, every
    relationship between them) across all users -- destructive, and not
    scoped to a single `user_id` like every other function in this module.

    Not a request-path function: the only caller is
    `backend/scripts/rebuild_graph_with_provenance.py` (Story 2.8's
    one-time operational rebuild), which requires its own explicit `--yes`
    flag before it will call this at all. Kept here, not as raw Cypher in
    that script, purely to hold AD-2's line ("no raw Cypher outside
    `neo4j_client.py`") -- it is not meant to be reused as a general-
    purpose reset, and no other caller should add itself here.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.execute_write(lambda tx: tx.run("MATCH (n:Entity) DETACH DELETE n").consume())


# Shared by every function in the read path below (Story: Graph Preview
# document filter). `{var}` is filled in with the Cypher variable the check
# applies to (`e` for an entity, `r` for a relationship) -- always format
# this constant on its own, before it's dropped into the surrounding query
# string, the same discipline `_APPEND_SOURCE_DOCUMENT_ID` above already
# follows. The surrounding queries contain literal `{user_id: $user_id}`
# braces, so calling `.format()` on the already-joined string would try to
# fill those in too and raise `KeyError: 'user_id'`.
#
# `size($document_ids) = 0` is the "no filter" escape hatch -- the Python
# side always passes a list (`get_graph_for_user` normalizes `None` to
# `[]`), so this only ever needs to check for empty, not `None`. A node or
# relationship with no `source_document_ids` at all (written before this
# property existed -- see `prune_document_from_graph`'s docstring) reads as
# `coalesce(..., [])`, which can never overlap a non-empty `$document_ids`,
# so it's excluded from any filtered selection and only ever visible in the
# unfiltered ("showing everything") default -- there's no document to
# attribute it to, so there's no other sound choice.
_MATCHES_DOCUMENT_SCOPE = (
    "(size($document_ids) = 0 OR any(id IN coalesce({var}.source_document_ids, []) WHERE id IN $document_ids))"
)


def get_graph_for_user(
    user_id: str, document_ids: list[str] | None = None, limit: int = GRAPH_NODE_LIMIT
) -> tuple[list[dict], list[dict], int]:
    """The read side of Story 4.1's Graph Preview, and the first Neo4j read
    path this codebase has -- `kg/service.py` is the only caller (AD-2: no
    module hand-writes Cypher of its own).

    `document_ids`, when non-empty, scopes every part of this read (entity
    count, entity list, each entity's `degree`, and relationships) to only
    what the given documents contributed -- an empty list or `None` (the
    default) preserves the original unfiltered "everything this user owns"
    behavior. Scoping is a *view* concern layered on top of AD-4's
    exact-match entity merge, not a change to it: an entity two selected
    documents both mention still renders as one shared node with edges from
    both, since merging still happens at write time. This does not validate
    that the given ids belong to `user_id` -- see `kg/routes.py`'s docstring
    for why that's unnecessary here.

    Returns `(entity_rows, relationship_rows, total_entity_count)`:

    - `entity_rows`: up to `limit` dicts (`name`, `type`, `degree`), the
      user's highest-degree entities first (ties broken by name, so the
      same `limit` entities come back on every call rather than an
      arbitrary subset among degree ties -- ties are common near the cut
      point of a large graph). An entity that's in scope but has zero
      in-scope relationships still appears here with `degree = 0` -- see
      `_get_entities_tx` for what that implies once the node cap is in
      play.
    - `relationship_rows`: dicts (`source_name`, `source_type`,
      `target_name`, `target_type`, `relationship_type`) for relationships
      whose *both* endpoints are among `entity_rows` **and** whose own
      `source_document_ids` overlaps `document_ids` when a filter is
      active -- both-endpoints-in-scope alone isn't enough, since two
      entities can each individually appear in the selected documents
      without any selected document having asserted a relationship between
      them specifically (it could've been asserted only by a document
      outside the selection). This is what keeps a filtered view from
      still showing connections the user didn't ask for. An entity that
      didn't survive the cap can't contribute a dangling edge either way.
      Also capped independently, at `GRAPH_EDGE_LIMIT` -- see that
      constant's comment for why edges need their own bound.
    - `total_entity_count`: the true count of entities *matching the
      current scope* (filtered or not) before capping, so the caller can
      render "showing top N of M" -- always scoped the same way
      `entity_rows` is, so a single-document selection reports that
      document's own total, never the whole account's.

    Returns dicts, not `Neo4jEntity`/`Neo4jRelationship` (see `shapes.py`)
    -- those are the write-side contract and don't carry the endpoint
    *types* or the `degree` this read path needs; forcing this data into
    them would mean adding fields Epic 2's writer never populates.

    Tenancy (AD-2): every query below filters `{user_id: $user_id}` on
    every `Entity` match -- the same guarantee `write_entities_and_
    relationships` and `weaviate_client.search_passages` already give,
    extended to the first read. `user_id` is always the caller-resolved
    value (`kg/service.py` reads it off `get_current_user`), never
    accepted from this function's own caller as client input.
    """
    document_ids = document_ids or []
    driver = get_neo4j_driver()
    with driver.session() as session:
        total_entity_count = session.execute_read(_get_entity_count_tx, user_id, document_ids)
        entity_rows = session.execute_read(_get_entities_tx, user_id, document_ids, limit)
        keep_ids = [f"{row['type']}:{row['name']}" for row in entity_rows]
        relationship_rows = session.execute_read(
            _get_relationships_tx, user_id, keep_ids, document_ids
        )
    return entity_rows, relationship_rows, total_entity_count


def _get_entity_count_tx(tx, user_id, document_ids: list[str]) -> int:
    result = tx.run(
        "MATCH (e:Entity {user_id: $user_id}) "
        f"WHERE {_MATCHES_DOCUMENT_SCOPE.format(var='e')} "
        "RETURN count(e) AS total",
        user_id=user_id,
        document_ids=document_ids,
    )
    return result.single()["total"]


def _get_entities_tx(tx, user_id, document_ids: list[str], limit) -> list[dict]:
    """Ranks by degree computed across the *whole matching scope* (not just
    the entities that end up surviving the cap), so "prominence" reflects
    true connectivity within that scope rather than an artifact of the cap
    itself. When `document_ids` is non-empty, both the entity (`e`) and the
    neighbor relationship (`r`) in the `OPTIONAL MATCH` are scoped -- degree
    must count only relationships the selected documents actually asserted,
    or a hub entity would keep rendering as a hub after filtering down to a
    document that never asserted most of its edges (the same "invented
    connection" problem, just expressed as node size instead of a drawn
    line).

    Consequence, not a bug: an in-scope entity with zero in-scope
    relationships gets `degree = 0`, sorts last, and is the first thing
    this cap drops once a selection's matching entity count exceeds
    `limit`. That's consistent with ranking by degree at all -- isolated
    entities are simply the least "prominent" under this metric.

    No `r IS NULL OR` guard needed on the `WHERE` below, even though it
    might look like one should protect a genuinely isolated entity from
    being filtered out: `OPTIONAL MATCH ... WHERE` behaves like a SQL LEFT
    JOIN's `ON` clause, not a post-hoc row filter -- when every candidate
    `r` for a given `e` fails the predicate (including the trivial case of
    no candidates at all), Neo4j substitutes a single null `r` for that
    `e` rather than dropping the row, so `e` always survives regardless of
    how the `WHERE` reads. The predicate below only ever discards
    individual out-of-scope `(e, r)` candidates; it can't discard `e`
    itself.
    """
    result = tx.run(
        "MATCH (e:Entity {user_id: $user_id}) "
        f"WHERE {_MATCHES_DOCUMENT_SCOPE.format(var='e')} "
        "OPTIONAL MATCH (e)-[r]-(:Entity {user_id: $user_id}) "
        f"WHERE {_MATCHES_DOCUMENT_SCOPE.format(var='r')} "
        "WITH e, count(r) AS degree "
        "ORDER BY degree DESC, e.name ASC "
        "LIMIT $limit "
        "RETURN e.name AS name, e.type AS type, degree",
        user_id=user_id,
        document_ids=document_ids,
        limit=limit,
    )
    return [{"name": record["name"], "type": record["type"], "degree": record["degree"]} for record in result]


def _get_relationships_tx(tx, user_id, keep_ids: list[str], document_ids: list[str]) -> list[dict]:
    """`keep_ids` are `"{type}:{name}"` strings for the entities the caller
    already decided to keep (post-cap) -- a relationship only comes back
    if *both* endpoints are in that set, so a dropped entity never leaves
    a dangling edge pointing at nothing rendered. When `document_ids` is
    non-empty, the relationship's own `source_document_ids` must also
    overlap it -- both-endpoints-in-scope is necessary but not sufficient,
    since a relationship between two in-scope entities could still have
    been asserted only by a document outside the current selection.

    No relationship *type* interpolation here, unlike the write path:
    `type(r)` is a Cypher function returning the type as a value, not
    syntax construction, so it needs no parameterization and reaches no
    `_SAFE_RELATIONSHIP_TYPE_RE`-style guard -- that regex exists solely
    because the write path's `MERGE (a)-[:{type}]->(b)` can't parameterize
    a type in *write* position.

    Skips the query entirely when `keep_ids` is empty (an empty-graph or
    all-isolated user) -- Cypher's `IN []` would just match nothing, but
    there's no reason to spend a round-trip proving that.

    Capped at `GRAPH_EDGE_LIMIT`, ordered deterministically (by endpoint
    names and relationship type, so the same edges come back on every
    call rather than an arbitrary subset) -- see `GRAPH_EDGE_LIMIT`'s own
    comment for why edges need a bound independent of the entity cap.
    Unlike `_get_entities_tx`, this doesn't rank by any notion of
    importance -- there's no equivalent signal for a relationship -- so a
    graph past the edge cap silently drops some of its lowest-sorting
    edges rather than surfacing a "showing top N of M" note the way the
    node cap does. Acceptable for a defensive ceiling this far past
    today's real graph sizes; revisit if it's ever actually hit.
    """
    if not keep_ids:
        return []
    result = tx.run(
        "MATCH (a:Entity {user_id: $user_id})-[r]->(b:Entity {user_id: $user_id}) "
        "WHERE (a.type + ':' + a.name) IN $keep_ids AND (b.type + ':' + b.name) IN $keep_ids "
        f"AND {_MATCHES_DOCUMENT_SCOPE.format(var='r')} "
        "RETURN a.name AS source_name, a.type AS source_type, "
        "b.name AS target_name, b.type AS target_type, "
        "type(r) AS relationship_type "
        "ORDER BY source_name, target_name, relationship_type "
        "LIMIT $edge_limit",
        user_id=user_id,
        keep_ids=keep_ids,
        document_ids=document_ids,
        edge_limit=GRAPH_EDGE_LIMIT,
    )
    return [
        {
            "source_name": record["source_name"],
            "source_type": record["source_type"],
            "target_name": record["target_name"],
            "target_type": record["target_type"],
            "relationship_type": record["relationship_type"],
        }
        for record in result
    ]
