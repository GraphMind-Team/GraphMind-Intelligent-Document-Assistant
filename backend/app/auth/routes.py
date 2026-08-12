from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.rate_limiter import RateLimiter, get_login_rate_limiter, get_register_rate_limiter
from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.shared.data_access import get_db_session
from app.shared.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(
    data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    limiter: RateLimiter = Depends(get_register_rate_limiter),
) -> RegisterResponse:
    # Per-IP only (no email component, unlike login) -- registration's
    # attack shape is one source trying many different emails, either to
    # enumerate existing accounts via the 409/201 split or to mass-create
    # accounts. No reset() on success: a given email can only ever
    # register once, so there's no "legitimate repeat" to exempt the way
    # login's reset() exempts a user's own repeat logins.
    client_ip = request.client.host if request.client else "unknown"
    limiter.check(client_ip)
    user = service.register_user(db, data)
    return RegisterResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    limiter: RateLimiter = Depends(get_login_rate_limiter),
) -> LoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    limiter.check(client_ip, data.email)
    user = service.authenticate_user(db, data.email, data.password)
    limiter.reset(client_ip, data.email)
    token = service.create_access_token(user.id)
    return LoginResponse(access_token=token, token_type="bearer")


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse.model_validate(current_user)
