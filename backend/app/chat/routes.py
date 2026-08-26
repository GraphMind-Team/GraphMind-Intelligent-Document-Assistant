"""Chat module routes (Story 3.1; `GET /history` added Story 3.4/AD-10;
session-nested `POST /ask` and `GET /history` plus `chat_sessions` CRUD
added for multi-session chat).

Every endpoint requires `Depends(get_current_user)` so `user_id` never
comes from client-supplied input (AD-2) -- resolution (and, for `/ask`,
generation) all happen inside `service.py`/`sessions_service.py`, scoped
to `current_user`. `session_id` path params are similarly resolved and
ownership-checked inside those service functions (404 on a foreign or
nonexistent id), never trusted as-is.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.chat import service, sessions_service
from app.chat.rate_limiter import (
    get_ask_concurrency_limiter,
    get_ask_daily_rate_limiter,
    get_ask_rate_limiter,
)
from app.chat.schemas import (
    AskRequest,
    AskResponse,
    ChatHistoryResponse,
    ChatSessionResponse,
    ChatSessionUpdateRequest,
    MessageFeedbackRequest,
    MessageFeedbackResponse,
)
from app.shared.data_access import get_db_session
from app.shared.models import User
from app.shared.rate_limiter import ConcurrencyLimiter, RateLimiter

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
def create_session(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    return sessions_service.create_session(db, current_user)


@router.get("/sessions", response_model=list[ChatSessionResponse])
def list_sessions(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[ChatSessionResponse]:
    return sessions_service.list_sessions(db, current_user)


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_session(
    session_id: uuid.UUID,
    data: ChatSessionUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    return sessions_service.rename_session(db, current_user, session_id, data.title)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    sessions_service.delete_session(db, current_user, session_id)
    return Response(status_code=204)


@router.post("/sessions/{session_id}/ask", response_model=AskResponse)
def ask(
    session_id: uuid.UUID,
    request: AskRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_ask_rate_limiter),
    daily_rate_limiter: RateLimiter = Depends(get_ask_daily_rate_limiter),
    concurrency_limiter: ConcurrencyLimiter = Depends(get_ask_concurrency_limiter),
) -> AskResponse:
    # Keyed by account, and sharing one budget with `edit_message` below --
    # see `chat/rate_limiter.py` for why this route needs both a rate and a
    # concurrency bound. The concurrency slot wraps the whole service call,
    # not just a part of it: unlike upload (where only the body read holds
    # the scarce resource), the scarce resource here is the threadpool
    # worker, which is held for the entire retrieval-plus-generation span.
    # Released via context manager even if generation raises mid-request.
    user_key = str(current_user.id)
    rate_limiter.check(user_key)
    daily_rate_limiter.check(user_key)
    with concurrency_limiter.slot(user_key):
        return service.ask_question(
            db, current_user, session_id, request.question, request.document_ids
        )


@router.get("/sessions/{session_id}/history", response_model=ChatHistoryResponse)
def history(
    session_id: uuid.UUID,
    cursor: str | None = None,
    # UX-DR29: the frontend always sends an explicit `limit` (3 on initial
    # load, 10 on each scroll-up page) -- `le=50` is a defensive cap on a
    # client-supplied value, same spirit as `AskRequest.document_ids`'s own
    # `max_length=200` (chat/schemas.py), not a measured number.
    limit: int | None = Query(default=None, ge=1, le=50),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatHistoryResponse:
    return service.get_history(db, current_user, session_id, cursor, limit)


@router.post("/sessions/{session_id}/messages/{message_id}/edit", response_model=AskResponse)
def edit_message(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    request: AskRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_ask_rate_limiter),
    daily_rate_limiter: RateLimiter = Depends(get_ask_daily_rate_limiter),
    concurrency_limiter: ConcurrencyLimiter = Depends(get_ask_concurrency_limiter),
) -> AskResponse:
    # The same three limiters, and deliberately the same shared budgets,
    # as `ask` above -- `service.edit_message` re-runs `ask_question` end
    # to end, so this is not the cheaper route it might look like, and a
    # separate allowance would just be a second way to spend the same
    # upstream quota and threadpool workers.
    user_key = str(current_user.id)
    rate_limiter.check(user_key)
    daily_rate_limiter.check(user_key)
    with concurrency_limiter.slot(user_key):
        return service.edit_message(
            db, current_user, session_id, message_id, request.question, request.document_ids
        )


@router.put("/messages/{message_id}/feedback", response_model=MessageFeedbackResponse)
def set_message_feedback(
    message_id: uuid.UUID,
    data: MessageFeedbackRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageFeedbackResponse:
    message = service.set_message_feedback(db, current_user, message_id, data.rating)
    return MessageFeedbackResponse.model_validate(message)
