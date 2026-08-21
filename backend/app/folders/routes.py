"""Folders module routes.

Four endpoints: `POST /folders` (create), `GET /folders` (list),
`PATCH /folders/{folder_id}` (rename/recolor), `DELETE /folders/{folder_id}`.
All require `Depends(get_current_user)` so `user_id` never comes from
client-supplied input (AD-2) -- mirrors `documents/routes.py`'s structure.
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.folders import service
from app.folders.schemas import FolderCreateRequest, FolderResponse, FolderUpdateRequest
from app.shared.data_access import get_db_session
from app.shared.models import User

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("", response_model=FolderResponse, status_code=201)
def create_folder(
    data: FolderCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> FolderResponse:
    folder = service.create_folder(db, current_user, data)
    return FolderResponse.model_validate(folder)


@router.get("", response_model=list[FolderResponse])
def list_folders(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[FolderResponse]:
    folders = service.list_folders(db, current_user)
    return [FolderResponse.model_validate(folder) for folder in folders]


@router.patch("/{folder_id}", response_model=FolderResponse)
def update_folder(
    folder_id: uuid.UUID,
    data: FolderUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> FolderResponse:
    folder = service.update_folder(db, current_user, folder_id, data)
    return FolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=204)
def delete_folder(
    folder_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    service.delete_folder(db, current_user, folder_id)
    return Response(status_code=204)
