"""add theme to users

Revision ID: d9814d322f6d
Revises: e1f5c8a2b4d7
Create Date: 2026-08-15 13:07:40.955797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9814d322f6d'
down_revision: Union[str, None] = 'e1f5c8a2b4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Constant default (unlike content_hash's staged nullable-then-backfill
    # migration, which needed a per-row computed value) -- a single
    # ADD COLUMN with server_default backfills every existing row and
    # satisfies NOT NULL in one statement.
    op.add_column('users', sa.Column('theme', sa.String(length=5), nullable=False, server_default='light'))


def downgrade() -> None:
    op.drop_column('users', 'theme')
