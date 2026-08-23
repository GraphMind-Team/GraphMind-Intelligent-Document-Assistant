"""Knowledge graph module business logic (Story 4.1; `document_ids` scoping
added for the graph document/folder filter).

Calls `shared/data_access/neo4j_client.get_graph_for_user` directly, the
same way `chat/service.py` calls `shared/data_access/weaviate_client.
search_passages` directly for its vector-store half rather than routing
through `chat/repository.py` -- nothing here needs Postgres, so
`kg/repository.py` stays the stub it's been since Story 1.1 (AD-2 requires
`shared/data_access` be the sole path to Neo4j; it does not require every
module's own `repository.py` to be non-empty).

Never imports `app.shared.llm_client` -- graph visualization is a pure
Cypher read (AD-6).
"""

import uuid

from app.kg.schemas import GraphEdge, GraphNode, GraphResponse
from app.shared.data_access.neo4j_client import get_graph_for_user
from app.shared.models import User


def _node_id(name: str, entity_type: str) -> str:
    return f"{entity_type}:{name}"


def get_graph(current_user: User, document_ids: list[uuid.UUID] | None = None) -> GraphResponse:
    """Assembles `GraphResponse` from the raw entity/relationship rows
    `get_graph_for_user` returns. `user_id` is resolved from
    `current_user` (itself resolved from the JWT by `get_current_user`),
    never accepted as a parameter from this function's own caller --
    `kg/routes.py` passes nothing else in.

    `document_ids` is client-supplied *scope*, not a tenancy input --
    tenancy stays `current_user.id` alone, the same as every other call
    this module makes. Stringified before being handed to
    `get_graph_for_user`, since Neo4j params are plain strings, not
    `uuid.UUID` objects."""
    document_id_strs = [str(document_id) for document_id in document_ids] if document_ids else []
    entity_rows, relationship_rows, total_node_count = get_graph_for_user(
        str(current_user.id), document_id_strs
    )

    nodes = [
        GraphNode(id=_node_id(row["name"], row["type"]), name=row["name"], type=row["type"], degree=row["degree"])
        for row in entity_rows
    ]
    edges = [
        GraphEdge(
            source=_node_id(row["source_name"], row["source_type"]),
            target=_node_id(row["target_name"], row["target_type"]),
            type=row["relationship_type"],
        )
        for row in relationship_rows
    ]
    return GraphResponse(nodes=nodes, edges=edges, total_node_count=total_node_count)
