"""Knowledge graph module routes (Story 4.1).

One endpoint: `GET /kg/graph`, behind Graph Preview. `Depends(get_current_
user)` only -- no `db: Session`, since nothing here reads Postgres
directly (`get_current_user` already resolves the user via its own
internal Postgres lookup). `user_id` never comes from client-supplied
input (AD-2); the endpoint takes no query parameters at all.
"""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.kg import service
from app.kg.schemas import GraphResponse
from app.shared.models import User

router = APIRouter(prefix="/kg", tags=["kg"])


@router.get("/graph", response_model=GraphResponse)
def get_graph(current_user: User = Depends(get_current_user)) -> GraphResponse:
    return service.get_graph(current_user)
