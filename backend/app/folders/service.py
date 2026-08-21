"""Folders module business logic.

Raises `HTTPException` directly (AD-3: no custom error envelope), mirroring
`auth/service.py` and `documents/service.py`. `name`/`color` validation
happens here rather than in a pydantic validator so a rejected value comes
back as a plain 400 (the spec's I/O matrix), not a 422 validation envelope
-- the same split `documents/service.py`'s `validate_format`/`validate_size`
already draw between "the route layer's job" and "this module's job".
"""

import uuid
from typing import Final

from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.folders import repository
from app.folders.schemas import FolderCreateRequest, FolderUpdateRequest
from app.shared.models import Folder, User

# The enforced pastel-color vocabulary (Design Notes): six named keys, small
# enough to render as a one-row swatch picker in `FolderModal.jsx`. Mirrors
# `Document.status`'s "vocabulary enforced in code, not schema" precedent --
# `color` is a plain `String` column, never a free-form client hex value
# (the spec's Never section). Each key must also exist as a
# `--folder-color-*` pastel token pair in `frontend/src/index.css`.
FOLDER_COLORS: Final = {"rose", "peach", "sun", "mint", "sky", "lilac"}

# Mirrors `FolderModal.jsx`'s `maxLength={255}` on the name input -- that
# only stops the in-app form, so a direct API call still needs the same
# ceiling enforced here (the `Folder.name` column is an unbounded
# `String`). A plain 400, not a pydantic `Field` constraint, for the same
# reason `_validate_color` below isn't one either: this module keeps its
# rejections on the `HTTPException(400)` path, never a 422 envelope.
MAX_NAME_LENGTH: Final = 255


def _validate_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Folder name must not be blank.")
    if len(stripped) > MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"Folder name must be at most {MAX_NAME_LENGTH} characters."
        )
    return stripped


def _validate_color(color: str) -> str:
    if color not in FOLDER_COLORS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid folder color. Supported colors: {', '.join(sorted(FOLDER_COLORS))}.",
        )
    return color


def list_folders(db: Session, current_user: User) -> list[Folder]:
    return repository.list_folders_for_user(db, current_user.id)


def get_folder(db: Session, current_user: User, folder_id: uuid.UUID) -> Folder:
    """One folder by id, or `HTTPException(404)`.

    404 -- not 403 -- for another account's folder, or an id that doesn't
    exist at all: same IDOR-safe convention `documents/service.py::get_document`
    already establishes, and the one the spec's I/O matrix names explicitly
    for both the folder endpoints and the document-assignment PATCH.
    """
    folder = repository.get_folder_for_user(db, current_user.id, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found.")
    return folder


def create_folder(db: Session, current_user: User, data: FolderCreateRequest) -> Folder:
    name = _validate_name(data.name)
    color = _validate_color(data.color)

    folder = Folder(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=name,
        color=color,
    )
    folder = repository.create_folder(db, folder)
    db.commit()
    db.refresh(folder)
    return folder


def update_folder(
    db: Session, current_user: User, folder_id: uuid.UUID, data: FolderUpdateRequest
) -> Folder:
    """Renames and/or recolors a folder in place. Either field may be
    omitted (`None`) to leave it unchanged -- `FolderModal.jsx` always
    submits both, but the PATCH itself supports a partial update."""
    folder = get_folder(db, current_user, folder_id)
    if data.name is not None:
        folder.name = _validate_name(data.name)
    if data.color is not None:
        folder.color = _validate_color(data.color)
    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, current_user: User, folder_id: uuid.UUID) -> None:
    """Deletes a folder. Its documents are never deleted -- `documents
    .folder_id`'s `ON DELETE SET NULL` unfiles them at the DB level, so
    there is no separate step here to unfile them by hand."""
    get_folder(db, current_user, folder_id)
    repository.delete_folder_for_user(db, current_user.id, folder_id)
    db.commit()
