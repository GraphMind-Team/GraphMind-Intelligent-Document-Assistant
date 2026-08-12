from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.schemas import RegisterRequest, RegisterResponse
from app.shared.data_access import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db_session)) -> RegisterResponse:
    user = service.register_user(db, data)
    return RegisterResponse.model_validate(user)
