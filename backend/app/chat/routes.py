"""Chat module routes (Story 3.1; `GET /history` added Story 3.4/AD-10).

Both endpoints require `Depends(get_current_user)` so `user_id` never
comes from client-supplied input (AD-2) -- resolution (and, for `/ask`,
generation) both happen inside `service.py`, scoped to `current_user`.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.chat import service
from app.chat.schemas import AskRequest, AskResponse, ChatHistoryResponse
from app.shared.data_access import get_db_session
from app.shared.models import User

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    return service.ask_question(db, current_user, request.question, request.document_ids)


@router.get("/history", response_model=ChatHistoryResponse)
def history(
    cursor: str | None = None,
    # UX-DR29: the frontend always sends an explicit `limit` (3 on initial
    # load, 10 on each scroll-up page) -- `le=50` is a defensive cap on a
    # client-supplied value, same spirit as `AskRequest.document_ids`'s own
    # `max_length=200` (chat/schemas.py), not a measured number.
    limit: int | None = Query(default=None, ge=1, le=50),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatHistoryResponse:
    return service.get_history(db, current_user, cursor, limit)
