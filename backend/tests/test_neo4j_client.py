"""`shared/data_access/neo4j_client.py` tests (Story 2.4 + Story 2.8): the
missing-config error, the driver singleton behavior, the empty-write no-op,
that an exact `(name, type, user_id)` match issues the identical `MERGE`
(so it would land on one node in a real database) while a near-match name
issues a distinct one, that a relationship whose entity can't be resolved
(not present in the same call's `entities`) is skipped rather than guessed
at, that an unsafe/unrecognized relationship type never reaches Cypher
interpolation, that every `MERGE` stamps `source_document_ids` (Story 2.8),
and `prune_document_from_graph`'s reference-counted delete. All isolated
from a real Neo4j connection via a fake driver/session/transaction,
mirroring `test_weaviate_client.py`'s approach.
"""

import re
from unittest.mock import MagicMock

import pytest

from app.shared.data_access import neo4j_client as neo4j_client_module
from app.shared.data_access.neo4j_client import (
    close_neo4j_driver,
    delete_entities_for_user,
    get_graph_for_user,
    get_neo4j_driver,
    prune_document_from_graph,
    write_entities_and_relationships,
)
from app.shared.data_access.shapes import Neo4jEntity, Neo4jRelationship


@pytest.fixture(autouse=True)
def _reset_module_singleton(monkeypatch):
    monkeypatch.setattr(neo4j_client_module, "_driver_instance", None)


class _FakeResult:
    """`tx.run(...)` returns a result the production code `.consume()`s --
    a bare `None` return here would `AttributeError` instead of exercising
    that call."""

    def __init__(self):
        self.consumed = False

    def consume(self):
        self.consumed = True
        return self


class _FakeTx:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.results: list[_FakeResult] = []

    def run(self, query, **params):
        self.calls.append((query, params))
        result = _FakeResult()
        self.results.append(result)
        return result


class _FakeSession:
    def __init__(self, tx):
        self._tx = tx

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute_write(self, fn, *args):
        return fn(self._tx, *args)

    def execute_read(self, fn, *args):
        return fn(self._tx, *args)


class _FakeDriver:
    def __init__(self):
        self.tx = _FakeTx()
        self.closed = False

    def session(self):
        return _FakeSession(self.tx)

    def close(self):
        self.closed = True


class _FakeReadResult:
    """Wraps a list of plain dicts -- production code reads records via
    `record["key"]` and, for the count query, `.single()`; a dict already
    satisfies `__getitem__`, so no separate fake "record" type is needed."""

    def __init__(self, records: list[dict]):
        self._records = records

    def __iter__(self):
        return iter(self._records)

    def single(self):
        return self._records[0]


class _FakeReadTx:
    """Returns pre-scripted results in call order -- `get_graph_for_user`
    issues its (count, entities, [relationships]) queries in a fixed
    sequence per call, so a plain queue is enough to stand in for a real
    transaction without modeling actual graph semantics."""

    def __init__(self, responses: list[list[dict]]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return _FakeReadResult(self._responses.pop(0))


class _FakeReadSession:
    def __init__(self, tx):
        self._tx = tx

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute_read(self, fn, *args):
        return fn(self._tx, *args)


class _FakeReadDriver:
    def __init__(self, tx):
        self._tx = tx

    def session(self):
        return _FakeReadSession(self._tx)


def test_get_neo4j_driver_raises_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        get_neo4j_driver()

    assert "NEO4J_URI" in str(excinfo.value)
    assert "NEO4J_USERNAME" in str(excinfo.value)
    assert "NEO4J_PASSWORD" in str(excinfo.value)


def test_get_neo4j_driver_returns_the_same_instance_on_repeat_calls(monkeypatch):
    created = []

    def _fake_driver_factory(uri, auth):
        driver = MagicMock()
        created.append(driver)
        return driver

    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    monkeypatch.setattr(neo4j_client_module.GraphDatabase, "driver", _fake_driver_factory)

    first = get_neo4j_driver()
    second = get_neo4j_driver()

    assert first is second
    assert len(created) == 1


def test_close_neo4j_driver_is_a_no_op_when_none_was_ever_built():
    close_neo4j_driver()  # must not raise, must not connect


def test_close_neo4j_driver_closes_and_clears_the_singleton(monkeypatch):
    fake_driver = MagicMock()
    monkeypatch.setattr(neo4j_client_module, "_driver_instance", fake_driver)

    close_neo4j_driver()

    fake_driver.close.assert_called_once()
    assert neo4j_client_module._driver_instance is None


def test_write_entities_and_relationships_empty_lists_never_touches_the_driver(monkeypatch):
    fake_getter = MagicMock()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", fake_getter)

    write_entities_and_relationships([], [], "user-1", "doc-1")

    fake_getter.assert_not_called()


def test_write_entities_and_relationships_rejects_an_entity_with_a_mismatched_user_id(monkeypatch):
    fake_getter = MagicMock()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", fake_getter)

    entities = [Neo4jEntity(name="Maria Ivanova", type="Person", user_id="someone-else")]

    with pytest.raises(ValueError):
        write_entities_and_relationships(entities, [], "user-1", "doc-1")

    fake_getter.assert_not_called()


def test_write_entities_and_relationships_rejects_a_relationship_with_a_mismatched_user_id(monkeypatch):
    fake_getter = MagicMock()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", fake_getter)

    relationships = [
        Neo4jRelationship(
            source_entity_name="A", target_entity_name="B", relationship_type="RELATED_TO", user_id="someone-else"
        )
    ]

    with pytest.raises(ValueError):
        write_entities_and_relationships([], relationships, "user-1", "doc-1")

    fake_getter.assert_not_called()


def test_write_entities_and_relationships_merges_each_entity(monkeypatch):
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1"),
        Neo4jEntity(name="TechCorp", type="Organization", user_id="user-1"),
    ]

    write_entities_and_relationships(entities, [], "user-1", "doc-1")

    # One batched UNWIND for every entity, not one round-trip each.
    assert len(fake_driver.tx.calls) == 1
    query, params = fake_driver.tx.calls[0]
    assert "UNWIND $rows AS row" in query
    assert "MERGE (e:Entity" in query
    assert params["user_id"] == "user-1"
    # Story 2.8: every MERGE stamps source_document_ids with the
    # contributing document's id.
    assert params["document_id"] == "doc-1"
    assert "source_document_ids" in query
    assert {row["name"] for row in params["rows"]} == {"Maria Ivanova", "TechCorp"}
    # The result is consumed, so a per-statement failure surfaces here
    # rather than later at commit.
    assert all(result.consumed for result in fake_driver.tx.results)


def test_write_entities_and_relationships_exact_match_issues_the_identical_merge(monkeypatch):
    """Two entities sharing `(name, type, user_id)` -- the story's "repeat
    entity across documents" scenario -- must produce identical `MERGE`
    rows, which is what makes them land on the same node in a real
    database."""
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1"),
        Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1"),
    ]

    write_entities_and_relationships(entities, [], "user-1", "doc-1")

    assert len(fake_driver.tx.calls) == 1
    _, params = fake_driver.tx.calls[0]
    first_row, second_row = params["rows"]
    assert first_row == second_row


def test_write_entities_and_relationships_near_match_name_stays_distinct(monkeypatch):
    """AD-4: no fuzzy merge -- "TechCorp" and "TechCorp Supplies" must be
    merged under different `name` values, so they land on distinct nodes
    rather than merging."""
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="TechCorp", type="Organization", user_id="user-1"),
        Neo4jEntity(name="TechCorp Supplies", type="Organization", user_id="user-1"),
    ]

    write_entities_and_relationships(entities, [], "user-1", "doc-1")

    _, params = fake_driver.tx.calls[0]
    names = [row["name"] for row in params["rows"]]
    assert names == ["TechCorp", "TechCorp Supplies"]


def test_write_entities_and_relationships_merges_a_relationship_between_two_entities(monkeypatch):
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1"),
        Neo4jEntity(name="TechCorp", type="Organization", user_id="user-1"),
    ]
    relationships = [
        Neo4jRelationship(
            source_entity_name="Maria Ivanova",
            target_entity_name="TechCorp",
            relationship_type="WORKS_AT",
            user_id="user-1",
        )
    ]

    write_entities_and_relationships(entities, relationships, "user-1", "doc-1")

    # 1 batched entity MERGE + 1 batched relationship MERGE for the single
    # relationship type present.
    assert len(fake_driver.tx.calls) == 2
    relationship_query, relationship_params = fake_driver.tx.calls[-1]
    assert "WORKS_AT" in relationship_query
    assert relationship_params["user_id"] == "user-1"
    # Story 2.8: relationships carry their own source_document_ids too.
    assert relationship_params["document_id"] == "doc-1"
    assert "source_document_ids" in relationship_query
    (row,) = relationship_params["rows"]
    assert row["source_name"] == "Maria Ivanova"
    assert row["source_type"] == "Person"
    assert row["target_name"] == "TechCorp"
    assert row["target_type"] == "Organization"


def test_write_entities_and_relationships_batches_relationships_by_type(monkeypatch):
    """The relationship *type* is the one thing Cypher can't parameterize,
    so it's the only reason more than one relationship statement is needed.
    Relationships must therefore be grouped by type -- 5 relationships
    across 2 types is 2 statements, not 5. With OD-1 closing the vocabulary
    at five types, this bounds the whole write at six queries regardless of
    document size."""
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1"),
        Neo4jEntity(name="Ivan Petrov", type="Person", user_id="user-1"),
        Neo4jEntity(name="TechCorp", type="Organization", user_id="user-1"),
        Neo4jEntity(name="Sofia", type="Location", user_id="user-1"),
    ]
    relationships = [
        Neo4jRelationship(
            source_entity_name="Maria Ivanova", target_entity_name="TechCorp",
            relationship_type="WORKS_AT", user_id="user-1",
        ),
        Neo4jRelationship(
            source_entity_name="Ivan Petrov", target_entity_name="TechCorp",
            relationship_type="WORKS_AT", user_id="user-1",
        ),
        Neo4jRelationship(
            source_entity_name="TechCorp", target_entity_name="Sofia",
            relationship_type="LOCATED_IN", user_id="user-1",
        ),
    ]

    write_entities_and_relationships(entities, relationships, "user-1", "doc-1")

    # 1 entity statement + 1 per distinct relationship type (2), not 4 + 3.
    assert len(fake_driver.tx.calls) == 3
    rows_by_query = {query: params["rows"] for query, params in fake_driver.tx.calls}
    works_at = next(rows for query, rows in rows_by_query.items() if "WORKS_AT" in query)
    located_in = next(rows for query, rows in rows_by_query.items() if "LOCATED_IN" in query)
    assert len(works_at) == 2
    assert len(located_in) == 1


def test_write_entities_and_relationships_skips_a_relationship_whose_entity_is_unresolved(
    monkeypatch, caplog
):
    """A relationship naming an entity absent from this call's `entities`
    can't be resolved to a type, so it's skipped (and logged), not merged
    with a guessed/missing type."""
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1")]
    relationships = [
        Neo4jRelationship(
            source_entity_name="Maria Ivanova",
            target_entity_name="Ghost Corp",  # never in `entities`
            relationship_type="WORKS_AT",
            user_id="user-1",
        )
    ]

    with caplog.at_level("WARNING"):
        write_entities_and_relationships(entities, relationships, "user-1", "doc-1")

    # Only the batched entity MERGE -- no relationship statement was
    # issued at all, since the one relationship was dropped.
    assert len(fake_driver.tx.calls) == 1
    assert "MERGE (e:Entity" in fake_driver.tx.calls[0][0]
    assert "Ghost Corp" in caplog.text


def test_write_entities_and_relationships_skips_a_relationship_whose_source_name_is_ambiguous(
    monkeypatch, caplog
):
    """AD-4: the same name can legitimately belong to two different-typed
    entities in one call (e.g. "Washington" the Person and "Washington"
    the Location). A relationship naming that ambiguous name can't be
    resolved to a single type -- it must be skipped (and logged), never
    silently matched against whichever entity happened to be seen last."""
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="Washington", type="Person", user_id="user-1"),
        Neo4jEntity(name="Washington", type="Location", user_id="user-1"),
        Neo4jEntity(name="TechCorp", type="Organization", user_id="user-1"),
    ]
    relationships = [
        Neo4jRelationship(
            source_entity_name="Washington",
            target_entity_name="TechCorp",
            relationship_type="WORKS_AT",
            user_id="user-1",
        )
    ]

    with caplog.at_level("WARNING"):
        write_entities_and_relationships(entities, relationships, "user-1", "doc-1")

    # The batched entity MERGE still carries all 3 entities, but no
    # relationship statement was issued -- "Washington" is ambiguous, not
    # absent, and must be dropped the same way.
    assert len(fake_driver.tx.calls) == 1
    assert len(fake_driver.tx.calls[0][1]["rows"]) == 3
    assert "Washington" in caplog.text


def test_write_entities_and_relationships_skips_an_unsafe_relationship_type(monkeypatch, caplog):
    """Defense-in-depth: even though `shared/llm_client` already validates
    against OD-1's closed set before this module is ever called, a
    relationship type that isn't a safe SCREAMING_SNAKE_CASE identifier
    must never reach Cypher string interpolation (the only way a
    relationship *type* -- as opposed to a property value -- can be
    parameterized with the Neo4j driver)."""
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="A", type="Person", user_id="user-1"),
        Neo4jEntity(name="B", type="Organization", user_id="user-1"),
    ]
    relationships = [
        Neo4jRelationship(
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="RELATED_TO}) DETACH DELETE (n",  # injection attempt
            user_id="user-1",
        )
    ]

    with caplog.at_level("WARNING"):
        write_entities_and_relationships(entities, relationships, "user-1", "doc-1")

    # Only the batched entity MERGE -- the unsafe relationship never
    # reached Cypher interpolation, so no relationship statement exists.
    assert len(fake_driver.tx.calls) == 1
    assert "DETACH DELETE" not in fake_driver.tx.calls[0][0]
    assert "unsafe" in caplog.text.lower()


def test_get_graph_for_user_returns_empty_for_a_user_with_no_entities(monkeypatch):
    fake_tx = _FakeReadTx([[{"total": 0}], []])
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    entities, relationships, total = get_graph_for_user("user-1")

    assert entities == []
    assert relationships == []
    assert total == 0
    # Count + entities only -- the relationships query is skipped
    # entirely when no entity survived to keep (empty `keep_ids`), rather
    # than spending a round-trip on a query `IN []` would answer empty
    # anyway.
    assert len(fake_tx.calls) == 2


def test_get_graph_for_user_returns_an_isolated_entity_at_zero_degree(monkeypatch):
    fake_tx = _FakeReadTx(
        [
            [{"total": 1}],
            [{"name": "Solo Corp", "type": "Organization", "degree": 0}],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    entities, relationships, total = get_graph_for_user("user-1")

    assert entities == [{"name": "Solo Corp", "type": "Organization", "degree": 0}]
    assert relationships == []
    assert total == 1

    # The relationships query, even with nothing to return, is still
    # issued once an entity survived the cap -- and it's scoped by the
    # entity's own `type:name` id.
    _, relationship_params = fake_tx.calls[-1]
    assert relationship_params["keep_ids"] == ["Organization:Solo Corp"]


def test_get_graph_for_user_relationship_row_carries_endpoint_types_via_type_function(monkeypatch):
    """`type(r)` is a Cypher function returning the relationship's type as
    a plain value -- unlike the write path, no type ever needs to be
    interpolated into this query's syntax, so no
    `_SAFE_RELATIONSHIP_TYPE_RE`-style guard is needed on the read side."""
    fake_tx = _FakeReadTx(
        [
            [{"total": 2}],
            [
                {"name": "Maria Ivanova", "type": "Person", "degree": 1},
                {"name": "TechCorp", "type": "Organization", "degree": 1},
            ],
            [
                {
                    "source_name": "Maria Ivanova",
                    "source_type": "Person",
                    "target_name": "TechCorp",
                    "target_type": "Organization",
                    "relationship_type": "WORKS_AT",
                }
            ],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    entities, relationships, total = get_graph_for_user("user-1")

    assert total == 2
    assert relationships == [
        {
            "source_name": "Maria Ivanova",
            "source_type": "Person",
            "target_name": "TechCorp",
            "target_type": "Organization",
            "relationship_type": "WORKS_AT",
        }
    ]
    relationship_query, _ = fake_tx.calls[-1]
    assert "type(r) AS relationship_type" in relationship_query
    # No relationship type string is ever interpolated into this query --
    # every value in it is a bound parameter.
    assert "WORKS_AT" not in relationship_query


def test_get_graph_for_user_scopes_every_match_to_user_id(monkeypatch):
    """The relationship query requires *both* endpoints to independently
    match `user_id` in the same pattern -- the same AND-filter tenancy
    guarantee the write path and `weaviate_client.search_passages` already
    give, extended to this first read."""
    fake_tx = _FakeReadTx([[{"total": 0}], []])
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    get_graph_for_user("user-1")

    count_query, count_params = fake_tx.calls[0]
    entities_query, entities_params = fake_tx.calls[1]
    assert "{user_id: $user_id}" in count_query
    assert count_params["user_id"] == "user-1"
    assert "{user_id: $user_id}" in entities_query
    assert entities_params["user_id"] == "user-1"


def test_get_graph_for_user_relationships_query_requires_both_endpoints_scoped(monkeypatch):
    fake_tx = _FakeReadTx(
        [
            [{"total": 1}],
            [{"name": "A", "type": "Person", "degree": 0}],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    get_graph_for_user("user-1")

    relationship_query, relationship_params = fake_tx.calls[-1]
    assert "(a:Entity {user_id: $user_id})" in relationship_query
    assert "(b:Entity {user_id: $user_id})" in relationship_query
    assert relationship_params["user_id"] == "user-1"


def test_get_graph_for_user_relationships_query_is_capped_and_ordered_deterministically(monkeypatch):
    """The entity cap (`GRAPH_NODE_LIMIT`) bounds entities, not edges --
    up to that many entities can still carry far more relationships
    between them than any UI or query budget should accept unbounded.
    `GRAPH_EDGE_LIMIT` is that bound; `ORDER BY` makes which edges survive
    it deterministic, the same reasoning as the entity cap's own
    tie-break."""
    fake_tx = _FakeReadTx(
        [
            [{"total": 1}],
            [{"name": "A", "type": "Person", "degree": 0}],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    get_graph_for_user("user-1")

    relationship_query, relationship_params = fake_tx.calls[-1]
    assert "ORDER BY source_name, target_name, relationship_type" in relationship_query
    assert "LIMIT $edge_limit" in relationship_query
    assert relationship_params["edge_limit"] == neo4j_client_module.GRAPH_EDGE_LIMIT


def test_get_graph_for_user_caps_and_tiebreaks_by_name(monkeypatch):
    """`ORDER BY degree DESC, e.name ASC` -- without the name tie-break,
    which of several equal-degree entities survives a `LIMIT` is
    nondeterministic, which would make the same account's graph render a
    different node set on every reload."""
    fake_tx = _FakeReadTx([[{"total": 500}], [], []])
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    get_graph_for_user("user-1", limit=150)

    entities_query, entities_params = fake_tx.calls[1]
    assert "ORDER BY degree DESC, e.name ASC" in entities_query
    assert "LIMIT $limit" in entities_query
    assert entities_params["limit"] == 150


def test_get_graph_for_user_total_reflects_the_true_uncapped_count(monkeypatch):
    fake_tx = _FakeReadTx(
        [
            [{"total": 3241}],
            [{"name": f"Entity {i}", "type": "Person", "degree": 0} for i in range(2)],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    entities, _, total = get_graph_for_user("user-1", limit=2)

    assert len(entities) == 2
    assert total == 3241


# ---------------------------------------------------------------------------
# Graph Preview document/folder filter: `document_ids` scoping.
#
# `_FakeReadTx` scripts fixed responses and doesn't interpret Cypher, so
# these tests (like the tenancy/ordering tests above) verify the query text
# and params `get_graph_for_user` actually sends, plus how it threads
# scripted rows through to its return value -- not live Neo4j filtering
# semantics, which this suite has no way to exercise without a real
# database. Manual verification against the running dev backend covers the
# actual filtering behavior end to end.
# ---------------------------------------------------------------------------


def test_get_graph_for_user_none_and_empty_document_ids_are_equivalent(monkeypatch):
    """`None` (the default) and `[]` must produce the identical unfiltered
    request -- `get_graph_for_user` normalizes `None` to `[]` once, up
    front, so the Cypher predicate itself never has to branch on `None`."""
    fake_tx_a = _FakeReadTx([[{"total": 0}], []])
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx_a))
    get_graph_for_user("user-1")

    fake_tx_b = _FakeReadTx([[{"total": 0}], []])
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx_b))
    get_graph_for_user("user-1", document_ids=[])

    for fake_tx in (fake_tx_a, fake_tx_b):
        count_params = fake_tx.calls[0][1]
        entities_params = fake_tx.calls[1][1]
        assert count_params["document_ids"] == []
        assert entities_params["document_ids"] == []


def test_get_graph_for_user_forwards_document_ids_to_count_and_entities_queries(monkeypatch):
    fake_tx = _FakeReadTx(
        [
            [{"total": 1}],
            [{"name": "Solo Corp", "type": "Organization", "degree": 0}],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    get_graph_for_user("user-1", document_ids=["doc-1", "doc-2"])

    count_query, count_params = fake_tx.calls[0]
    entities_query, entities_params = fake_tx.calls[1]
    assert count_params["document_ids"] == ["doc-1", "doc-2"]
    assert entities_params["document_ids"] == ["doc-1", "doc-2"]
    # Both queries scope entities by the exact same predicate shape (not
    # two independently-drifted copies) -- this is what keeps a scoped
    # `total_node_count` consistent with the scoped `entity_rows` it's
    # meant to describe ("showing top N of M" must count the same M).
    entity_scope_clause = "any(id IN coalesce(e.source_document_ids, []) WHERE id IN $document_ids)"
    assert entity_scope_clause in count_query
    assert entity_scope_clause in entities_query


def test_get_graph_for_user_entities_query_scopes_the_degree_relationship_too(monkeypatch):
    """Degree must be computed over only in-scope relationships -- not just
    in-scope entities -- or a hub entity keeps its full-graph degree after
    filtering down to a document that never asserted most of its edges."""
    fake_tx = _FakeReadTx([[{"total": 0}], []])
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    get_graph_for_user("user-1", document_ids=["doc-1"])

    entities_query, _ = fake_tx.calls[1]
    assert "OPTIONAL MATCH (e)-[r]-(:Entity {user_id: $user_id})" in entities_query
    # The `r`-scope check is ORed with `r IS NULL` -- a genuinely isolated
    # entity (no relationship at all) must not be excluded by this WHERE,
    # only an out-of-scope relationship should be nulled out of the count.
    assert "WHERE r IS NULL OR" in entities_query
    assert "any(id IN coalesce(r.source_document_ids, []) WHERE id IN $document_ids)" in entities_query


def test_get_graph_for_user_relationships_query_requires_the_relationships_own_scope(monkeypatch):
    """The stricter, user-confirmed rule: both endpoints being in-scope is
    not enough -- the relationship itself must have been asserted by a
    selected document, or a relationship asserted only by an excluded
    document could still render just because its two endpoints happen to
    also appear in the current selection via unrelated documents."""
    fake_tx = _FakeReadTx(
        [
            [{"total": 1}],
            [{"name": "A", "type": "Person", "degree": 0}],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    get_graph_for_user("user-1", document_ids=["doc-1"])

    relationship_query, relationship_params = fake_tx.calls[-1]
    assert "(a.type + ':' + a.name) IN $keep_ids AND (b.type + ':' + b.name) IN $keep_ids" in relationship_query
    assert "AND (size($document_ids) = 0 OR any(id IN coalesce(r.source_document_ids, []) WHERE id IN $document_ids))" in relationship_query
    assert relationship_params["document_ids"] == ["doc-1"]


def test_get_graph_for_user_returns_an_isolated_entity_under_a_filter(monkeypatch):
    """An entity can pass the (scoped) entity filter while none of its
    relationships pass the stricter relationship filter -- it must still
    come back as a node, just with no edges, not be dropped entirely."""
    fake_tx = _FakeReadTx(
        [
            [{"total": 1}],
            [{"name": "Solo Corp", "type": "Organization", "degree": 0}],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    entities, relationships, total = get_graph_for_user("user-1", document_ids=["doc-1"])

    assert entities == [{"name": "Solo Corp", "type": "Organization", "degree": 0}]
    assert relationships == []
    assert total == 1


def test_get_graph_for_user_total_node_count_comes_from_the_scoped_count_query(monkeypatch):
    """`total_node_count` must reflect the *scoped* count, independent of
    how many entities the (separately capped) entities query returns --
    otherwise a single-document selection could report the whole account's
    total and the "showing top N of M" UI would misleadingly suggest more
    is being hidden than actually exists in scope."""
    fake_tx = _FakeReadTx(
        [
            [{"total": 3}],
            [{"name": "A", "type": "Person", "degree": 0}, {"name": "B", "type": "Person", "degree": 0}],
            [],
        ]
    )
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: _FakeReadDriver(fake_tx))

    entities, _, total = get_graph_for_user("user-1", document_ids=["doc-1"], limit=2)

    assert len(entities) == 2
    assert total == 3
    assert fake_tx.calls[0][1]["document_ids"] == ["doc-1"]


# ---------------------------------------------------------------------------
# Story 2.8: `source_document_ids` provenance + `prune_document_from_graph`.
#
# `_FakeTx` above only records calls for query-shape assertions -- it has
# no notion of graph state, so it can't tell "entity survives" from "entity
# deleted". `_GraphFakeTx` below is a second fake, independent of
# `neo4j_client.py`'s own implementation, that actually interprets the four
# fixed Cypher shapes that module issues (entity MERGE, relationship MERGE,
# relationship prune, entity prune) against an in-memory dict -- so these
# tests exercise real reference-counting outcomes, not just query text.
# ---------------------------------------------------------------------------


class _GraphFakeTx:
    def __init__(self):
        # (name, type, user_id) -> source_document_ids
        self.entities: dict[tuple[str, str, str], list[str]] = {}
        # (source_name, source_type, target_name, target_type, rel_type, user_id) -> source_document_ids
        self.relationships: dict[tuple[str, str, str, str, str, str], list[str]] = {}

    def run(self, query, **params):
        if "MERGE (e:Entity" in query:
            self._merge_entities(params)
        elif "MERGE (a)-[r:" in query:
            self._merge_relationship(query, params)
        elif "DELETE r" in query:
            self._prune_relationships(params)
        elif "DETACH DELETE e" in query:
            self._prune_entities(params)
        else:
            raise AssertionError(f"Unrecognized query shape in test fake: {query}")
        return MagicMock()

    def _merge_entities(self, params):
        user_id = params["user_id"]
        document_id = params["document_id"]
        for row in params["rows"]:
            ids = self.entities.setdefault((row["name"], row["type"], user_id), [])
            if document_id not in ids:
                ids.append(document_id)

    def _merge_relationship(self, query, params):
        rel_type = re.search(r"\[r:([A-Z_][A-Z0-9_]*)\]", query).group(1)
        user_id = params["user_id"]
        document_id = params["document_id"]
        for row in params["rows"]:
            key = (
                row["source_name"], row["source_type"],
                row["target_name"], row["target_type"],
                rel_type, user_id,
            )
            ids = self.relationships.setdefault(key, [])
            if document_id not in ids:
                ids.append(document_id)

    def _prune_relationships(self, params):
        user_id = params["user_id"]
        document_id = params["document_id"]
        for key in list(self.relationships.keys()):
            if key[-1] != user_id:
                continue
            ids = self.relationships[key]
            if document_id in ids:
                ids.remove(document_id)
                if not ids:
                    del self.relationships[key]

    def _prune_entities(self, params):
        user_id = params["user_id"]
        document_id = params["document_id"]
        for key in list(self.entities.keys()):
            if key[-1] != user_id:
                continue
            ids = self.entities[key]
            if document_id in ids:
                ids.remove(document_id)
                if not ids:
                    del self.entities[key]


class _GraphFakeSession:
    def __init__(self, tx):
        self._tx = tx

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute_write(self, fn, *args):
        return fn(self._tx, *args)


class _GraphFakeDriver:
    """Unlike `_FakeDriver`, persists one `_GraphFakeTx` across every
    `session()`/`execute_write()` call -- so a test can call
    `write_entities_and_relationships` and `prune_document_from_graph`
    multiple times in sequence and see their combined effect on the same
    underlying state, the way multiple calls against a real database would.
    """

    def __init__(self):
        self.tx = _GraphFakeTx()

    def session(self):
        return _GraphFakeSession(self.tx)


def test_write_entities_and_relationships_reingest_does_not_duplicate_source_document_ids(
    monkeypatch,
):
    """Story 2.6's reingest-on-Failed path writes the same document's
    entities twice -- `source_document_ids` must gain one entry, not two."""
    fake_driver = _GraphFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [Neo4jEntity(name="Repeat Corp", type="Organization", user_id="user-1")]

    write_entities_and_relationships(entities, [], "user-1", "doc-1")
    write_entities_and_relationships(entities, [], "user-1", "doc-1")

    assert fake_driver.tx.entities[("Repeat Corp", "Organization", "user-1")] == ["doc-1"]


def test_prune_document_from_graph_removes_an_entity_unique_to_the_deleted_document(monkeypatch):
    fake_driver = _GraphFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [Neo4jEntity(name="Solo Corp", type="Organization", user_id="user-1")]
    write_entities_and_relationships(entities, [], "user-1", "doc-1")

    prune_document_from_graph("doc-1", "user-1")

    assert fake_driver.tx.entities == {}


def test_prune_document_from_graph_keeps_an_entity_shared_by_a_surviving_document(monkeypatch):
    fake_driver = _GraphFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [Neo4jEntity(name="Shared Corp", type="Organization", user_id="user-1")]
    write_entities_and_relationships(entities, [], "user-1", "doc-1")
    write_entities_and_relationships(entities, [], "user-1", "doc-2")

    prune_document_from_graph("doc-1", "user-1")

    assert fake_driver.tx.entities[("Shared Corp", "Organization", "user-1")] == ["doc-2"]


def test_prune_document_from_graph_keeps_a_relationship_shared_by_a_surviving_document(
    monkeypatch,
):
    fake_driver = _GraphFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1"),
        Neo4jEntity(name="TechCorp", type="Organization", user_id="user-1"),
    ]
    relationships = [
        Neo4jRelationship(
            source_entity_name="Maria Ivanova",
            target_entity_name="TechCorp",
            relationship_type="WORKS_AT",
            user_id="user-1",
        )
    ]
    write_entities_and_relationships(entities, relationships, "user-1", "doc-1")
    write_entities_and_relationships(entities, relationships, "user-1", "doc-2")

    prune_document_from_graph("doc-1", "user-1")

    rel_key = ("Maria Ivanova", "Person", "TechCorp", "Organization", "WORKS_AT", "user-1")
    assert fake_driver.tx.relationships[rel_key] == ["doc-2"]
    # Both endpoint entities also survive via doc-2.
    assert fake_driver.tx.entities[("Maria Ivanova", "Person", "user-1")] == ["doc-2"]
    assert fake_driver.tx.entities[("TechCorp", "Organization", "user-1")] == ["doc-2"]


def test_prune_document_from_graph_is_idempotent_on_a_repeated_call(monkeypatch):
    fake_driver = _GraphFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [Neo4jEntity(name="Solo Corp", type="Organization", user_id="user-1")]
    write_entities_and_relationships(entities, [], "user-1", "doc-1")

    prune_document_from_graph("doc-1", "user-1")
    prune_document_from_graph("doc-1", "user-1")  # must not raise; nothing left to remove

    assert fake_driver.tx.entities == {}


def test_prune_document_from_graph_on_a_document_that_contributed_nothing_is_a_no_op(monkeypatch):
    fake_driver = _GraphFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [Neo4jEntity(name="Untouched Corp", type="Organization", user_id="user-1")]
    write_entities_and_relationships(entities, [], "user-1", "doc-1")

    prune_document_from_graph("doc-2", "user-1")  # doc-2 never contributed anything

    assert fake_driver.tx.entities[("Untouched Corp", "Organization", "user-1")] == ["doc-1"]


# ---------------------------------------------------------------------------
# Story 5.3: `delete_entities_for_user` (account-deletion cascade).
# ---------------------------------------------------------------------------


def test_delete_entities_for_user_issues_a_user_scoped_detach_delete(monkeypatch):
    """Query-shape check, mirroring how `write_entities_and_relationships`'s
    own tests assert on `fake_driver.tx.calls` -- a plain `MATCH (e:Entity
    {user_id: $user_id}) DETACH DELETE e`, no `document_id` anywhere (unlike
    `prune_document_from_graph`'s reference-counted, per-document query)."""
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    delete_entities_for_user("user-1")

    assert len(fake_driver.tx.calls) == 1
    query, params = fake_driver.tx.calls[0]
    assert "MATCH (e:Entity {user_id: $user_id})" in query
    assert "DETACH DELETE e" in query
    assert params["user_id"] == "user-1"
    assert fake_driver.tx.results[0].consumed is True


class _UserScopedFakeTx:
    """Minimal in-memory fake, independent of `_GraphFakeTx` (whose
    `DETACH DELETE e` branch assumes a `document_id` param that this
    story's whole-user delete never sends) -- interprets just the two
    shapes this test needs: the entity `MERGE` and this file's new
    `DETACH DELETE e` (user-scoped, no `document_id`)."""

    def __init__(self):
        self.entities: dict[tuple[str, str, str], list[str]] = {}

    def run(self, query, **params):
        if "MERGE (e:Entity" in query:
            user_id = params["user_id"]
            document_id = params["document_id"]
            for row in params["rows"]:
                ids = self.entities.setdefault((row["name"], row["type"], user_id), [])
                if document_id not in ids:
                    ids.append(document_id)
        elif "DETACH DELETE e" in query:
            user_id = params["user_id"]
            for key in list(self.entities.keys()):
                if key[-1] == user_id:
                    del self.entities[key]
        else:
            raise AssertionError(f"Unrecognized query shape in test fake: {query}")
        return MagicMock()


class _UserScopedFakeSession:
    def __init__(self, tx):
        self._tx = tx

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute_write(self, fn, *args):
        return fn(self._tx, *args)


class _UserScopedFakeDriver:
    def __init__(self):
        self.tx = _UserScopedFakeTx()

    def session(self):
        return _UserScopedFakeSession(self.tx)


def test_delete_entities_for_user_removes_only_that_users_entities(monkeypatch):
    fake_driver = _UserScopedFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    write_entities_and_relationships(
        [Neo4jEntity(name="User One Corp", type="Organization", user_id="user-1")],
        [],
        "user-1",
        "doc-1",
    )
    write_entities_and_relationships(
        [Neo4jEntity(name="User Two Corp", type="Organization", user_id="user-2")],
        [],
        "user-2",
        "doc-2",
    )

    delete_entities_for_user("user-1")

    assert ("User One Corp", "Organization", "user-1") not in fake_driver.tx.entities
    # A different user's entities are untouched.
    assert fake_driver.tx.entities[("User Two Corp", "Organization", "user-2")] == ["doc-2"]


def test_delete_entities_for_user_is_idempotent_on_a_repeated_call(monkeypatch):
    fake_driver = _UserScopedFakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    write_entities_and_relationships(
        [Neo4jEntity(name="Solo Corp", type="Organization", user_id="user-1")], [], "user-1", "doc-1"
    )

    delete_entities_for_user("user-1")
    delete_entities_for_user("user-1")  # must not raise; nothing left to remove

    assert fake_driver.tx.entities == {}
