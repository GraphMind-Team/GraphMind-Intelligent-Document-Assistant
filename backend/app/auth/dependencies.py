"""Resolves the authenticated user from the JWT in the Authorization
header. Route-layer wiring (not business logic, which stays in
service.py) -- lives here so it's reusable across every future protected
route in every module (documents, chat, kg) via `Depends(get_current_user)`.

Ordering inside `get_current_user` is deliberate: an absent/malformed/
expired token is rejected with 401 *before* `repository.get_user_by_id`
(the only DB call in this function) ever runs -- so AC4's "401 before any
data access" holds even for the auth check itself, not just for the
protected route's own data.
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import repository, service
from app.shared.data_access import get_db_session
from app.shared.models import User

# auto_error=False: HTTPBearer's default behavior raises 403 on a missing
# header, but AC4 requires 401 for an absent token -- so the missing case
# is intercepted here instead of trusting the default.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db_session),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    user_id = service.decode_access_token(credentials.credentials)

    user = repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user
