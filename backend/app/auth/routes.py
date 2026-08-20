from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.rate_limiter import (
    RateLimiter,
    get_change_password_rate_limiter,
    get_login_rate_limiter,
    get_register_rate_limiter,
    get_resend_verification_ip_rate_limiter,
    get_resend_verification_rate_limiter,
)
from app.auth.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    ProfileResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ThemeResponse,
    UpdateProfileRequest,
    UpdateThemeRequest,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.shared.data_access import get_db_session
from app.shared.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(
    data: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
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
    # Story 1.6: scheduled as a background task, same pattern as
    # documents.routes' ingest_document -- sending mail (an SMTP round
    # trip, up to 10s) must not hold the 201 response open, and a mail
    # outage must not turn a successful registration into a failed one.
    background_tasks.add_task(service.send_verification_email, user.id, user.email, user.full_name)
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
    return LoginResponse(access_token=token, token_type="bearer", theme=user.theme)


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse.model_validate(current_user)


@router.patch("/theme", response_model=ThemeResponse)
def update_theme(
    data: UpdateThemeRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ThemeResponse:
    service.update_theme(db, current_user, data.theme)
    return ThemeResponse(theme=data.theme)


@router.patch("/me", response_model=ProfileResponse)
def update_me(
    data: UpdateProfileRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    user = service.update_profile(db, current_user, data)
    return ProfileResponse.model_validate(user)


@router.post("/me/password", response_model=ChangePasswordResponse)
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_change_password_rate_limiter),
) -> ChangePasswordResponse:
    # Keyed by user id, not IP: the caller already holds a valid access
    # token here (get_current_user ran first), so the attack this guards
    # against is that token being used to brute-force current_password
    # against the one account it belongs to -- not an anonymous source
    # grinding many accounts, which is what login/register's IP-based keys
    # guard against instead.
    limiter.check(str(current_user.id))
    service.change_password(db, current_user, data)
    return ChangePasswordResponse()


@router.delete("/me", status_code=204)
def delete_me(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Hard-deletes the caller's own account and everything they own
    (Story 5.3) -- see `service.delete_account` for the fixed delete order
    and the mid-ingestion 409 guard."""
    service.delete_account(db, current_user)
    return Response(status_code=204)


@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(
    data: VerifyEmailRequest,
    db: Session = Depends(get_db_session),
) -> VerifyEmailResponse:
    """POST, not GET -- a GET link is fetched ahead of the human by mail-
    scanner/link-preview bots, silently burning a single-use-feeling token
    before anyone actually clicks. The frontend's VerifyEmailPage reads
    `?token=` from its own URL and issues this POST."""
    service.verify_email(db, data.token)
    return VerifyEmailResponse()


@router.post("/resend-verification", response_model=ResendVerificationResponse, status_code=202)
def resend_verification(
    data: ResendVerificationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    limiter: RateLimiter = Depends(get_resend_verification_rate_limiter),
    ip_limiter: RateLimiter = Depends(get_resend_verification_ip_rate_limiter),
) -> ResendVerificationResponse:
    # Two limiters, two attack shapes -- see rate_limiter.py's module
    # docstring. The (IP, email) pair check bounds spam against any one
    # victim's inbox; the IP-only check (register's own shape) bounds a
    # single source rotating through many target emails, which the pair
    # key alone doesn't cap. Always answers the same fixed 202 body
    # regardless of whether the account exists or is already verified
    # (service.resend_verification enforces that silently) -- this
    # response must not become an account-enumeration oracle. No `db`
    # dependency here -- unlike verify_email above, the actual send happens
    # in a background task (service.resend_verification opens its own
    # session), since an SMTP round trip must not hold this response open.
    client_ip = request.client.host if request.client else "unknown"
    ip_limiter.check(client_ip)
    limiter.check(client_ip, data.email)
    background_tasks.add_task(service.resend_verification, data.email)
    return ResendVerificationResponse()
