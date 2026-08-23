"""Knowledge graph module routes (Story 4.1; `document_ids` filter added for
the graph document/folder scope feature).

One endpoint: `GET /kg/graph`, behind Graph Preview. `Depends(get_current_
user)` only -- no `db: Session`, since nothing here reads Postgres
directly (`get_current_user` already resolves the user via its own
internal Postgres lookup). `user_id` never comes from client-supplied
input (AD-2).
"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.kg import service
from app.kg.schemas import GraphResponse
from app.shared.models import User

router = APIRouter(prefix="/kg", tags=["kg"])


@router.get("/graph", response_model=GraphResponse)
def get_graph(
    # Repeated-param style (`?document_ids=<uuid>&document_ids=<uuid>`), not
    # comma-joined and not a `folder_id` -- the frontend resolves folder ->
    # document ids client-side, so this module never needs a Postgres/folder
    # dependency of its own. Empty (the default) means "no filter," matching
    # `get_graph_for_user`'s own unfiltered-by-default behavior. `max_length`
    # is a defensive cap, same spirit as `AskRequest.document_ids`'s own
    # `max_length=200` (chat/schemas.py), not a measured number.
    #
    # No ownership validation against `current_user` -- same precedent as
    # `AskRequest.document_ids`: the `{user_id: $user_id}` match already
    # scopes every Neo4j query to this user, and `source_document_ids` is
    # only ever populated by `write_entities_and_relationships` under a
    # document's real owner, so a foreign or stale id simply matches
    # nothing server-side rather than needing a second, redundant check.
    document_ids: list[uuid.UUID] = Query(default=[], max_length=200),
    current_user: User = Depends(get_current_user),
) -> GraphResponse:
    return service.get_graph(current_user, document_ids)
