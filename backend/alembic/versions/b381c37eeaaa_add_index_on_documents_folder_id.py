"""add index on documents.folder_id

Revision ID: b381c37eeaaa
Revises: f3a8c1d9b6e2
Create Date: 2026-08-21 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b381c37eeaaa'
down_revision: Union[str, None] = 'f3a8c1d9b6e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres doesn't auto-index FK columns, and `documents.folder_id`'s
    # `ON DELETE SET NULL` needs one -- without it, deleting a folder forces
    # a full-table scan of `documents` to find its members. Mirrors every
    # other FK/user-scoping column in `shared/models.py`
    # (`documents_user_id`, `folders_user_id`, etc.), all of which already
    # carry an index.
    op.create_index(op.f('ix_documents_folder_id'), 'documents', ['folder_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_folder_id'), table_name='documents')
