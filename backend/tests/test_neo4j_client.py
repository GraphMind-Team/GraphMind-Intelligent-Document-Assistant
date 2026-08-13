"""`shared/data_access/neo4j_client.py` tests (Story 2.4): the missing-
config error, the driver singleton behavior, the empty-write no-op, that
an exact `(name, type, user_id)` match issues the identical `MERGE` (so it
would land on one node in a real database) while a near-match name issues
a distinct one, that a relationship whose entity can't be resolved (not
present in the same call's `entities`) is skipped rather than guessed at,
and that an unsafe/unrecognized relationship type never reaches Cypher
interpolation. All isolated from a real Neo4j connection via a fake
driver/session/transaction, mirroring `test_weaviate_client.py`'s approach.
"""

from unittest.mock import MagicMock

import pytest

from app.shared.data_access import neo4j_client as neo4j_client_module
from app.shared.data_access.neo4j_client import (
    close_neo4j_driver,
    get_neo4j_driver,
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


class _FakeDriver:
    def __init__(self):
        self.tx = _FakeTx()
        self.closed = False

    def session(self):
        return _FakeSession(self.tx)

    def close(self):
        self.closed = True


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

    write_entities_and_relationships([], [], "user-1")

    fake_getter.assert_not_called()


def test_write_entities_and_relationships_rejects_an_entity_with_a_mismatched_user_id(monkeypatch):
    fake_getter = MagicMock()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", fake_getter)

    entities = [Neo4jEntity(name="Maria Ivanova", type="Person", user_id="someone-else")]

    with pytest.raises(ValueError):
        write_entities_and_relationships(entities, [], "user-1")

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
        write_entities_and_relationships([], relationships, "user-1")

    fake_getter.assert_not_called()


def test_write_entities_and_relationships_merges_each_entity(monkeypatch):
    fake_driver = _FakeDriver()
    monkeypatch.setattr(neo4j_client_module, "get_neo4j_driver", lambda: fake_driver)

    entities = [
        Neo4jEntity(name="Maria Ivanova", type="Person", user_id="user-1"),
        Neo4jEntity(name="TechCorp", type="Organization", user_id="user-1"),
    ]

    write_entities_and_relationships(entities, [], "user-1")

    # One batched UNWIND for every entity, not one round-trip each.
    assert len(fake_driver.tx.calls) == 1
    query, params = fake_driver.tx.calls[0]
    assert "UNWIND $rows AS row" in query
    assert "MERGE (e:Entity" in query
    assert params["user_id"] == "user-1"
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

    write_entities_and_relationships(entities, [], "user-1")

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

    write_entities_and_relationships(entities, [], "user-1")

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

    write_entities_and_relationships(entities, relationships, "user-1")

    # 1 batched entity MERGE + 1 batched relationship MERGE for the single
    # relationship type present.
    assert len(fake_driver.tx.calls) == 2
    relationship_query, relationship_params = fake_driver.tx.calls[-1]
    assert "WORKS_AT" in relationship_query
    assert relationship_params["user_id"] == "user-1"
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

    write_entities_and_relationships(entities, relationships, "user-1")

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
        write_entities_and_relationships(entities, relationships, "user-1")

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
        write_entities_and_relationships(entities, relationships, "user-1")

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
        write_entities_and_relationships(entities, relationships, "user-1")

    # Only the batched entity MERGE -- the unsafe relationship never
    # reached Cypher interpolation, so no relationship statement exists.
    assert len(fake_driver.tx.calls) == 1
    assert "DETACH DELETE" not in fake_driver.tx.calls[0][0]
    assert "unsafe" in caplog.text.lower()
