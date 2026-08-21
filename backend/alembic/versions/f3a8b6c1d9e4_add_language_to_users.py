"""add language to users

Revision ID: f3a8b6c1d9e4
Revises: b381c37eeaaa
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8b6c1d9e4'
down_revision: Union[str, None] = 'b381c37eeaaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mirrors d9814d322f6d's theme-column migration: a constant default
    # backfills every existing row and satisfies NOT NULL in one statement.
    op.add_column('users', sa.Column('language', sa.String(length=5), nullable=False, server_default='en'))


def downgrade() -> None:
    op.drop_column('users', 'language')
