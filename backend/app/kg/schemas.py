"""Pydantic response models for the `kg` (knowledge graph) module (Story
4.1). One response schema -- `GET /kg/graph` has no request body.
"""

from pydantic import BaseModel


class GraphNode(BaseModel):
    # `f"{type}:{name}"` -- `Neo4jEntity` is only unique per
    # `(name, type, user_id)` (AD-4: two different-typed entities can
    # legitimately share a name), so bare `name` can't serve as a stable id.
    id: str
    name: str
    type: str
    # True whole-graph degree (count of relationships touching this
    # entity), computed before Story 4.1's node cap is applied -- the
    # frontend maps this to node diameter. Not scoped to only the edges
    # actually returned below; see `GraphResponse`'s own note.
    degree: int


class GraphEdge(BaseModel):
    source: str  # GraphNode.id
    target: str  # GraphNode.id
    type: str


class GraphResponse(BaseModel):
    # Capped at `neo4j_client.GRAPH_NODE_LIMIT`, highest-degree first.
    nodes: list[GraphNode]
    # Only between nodes that survived the cap -- a node's `degree` can
    # therefore exceed the number of edges actually drawn to/from it in
    # this response, when some of its real relationships point at an
    # entity that didn't make the cut. Deliberate (node size stays an
    # honest whole-graph signal); the frontend states this explicitly
    # rather than letting it read as a rendering bug.
    edges: list[GraphEdge]
    # The true entity count before capping -- equals `len(nodes)` when
    # under the cap, larger otherwise, so the UI can say "showing top N of
    # M."
    total_node_count: int
