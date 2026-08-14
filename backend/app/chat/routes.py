"""Chat module routes (Story 3.1).

One endpoint: `POST /chat/ask`. Requires `Depends(get_current_user)` so
`user_id` never comes from client-supplied input (AD-2) -- resolution and
generation both happen inside `service.ask_question`, scoped to
`current_user`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.chat import service
from app.chat.schemas import AskRequest, AskResponse
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
