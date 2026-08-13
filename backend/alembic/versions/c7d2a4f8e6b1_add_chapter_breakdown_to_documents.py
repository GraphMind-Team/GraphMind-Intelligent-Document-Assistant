"""add chapter_breakdown to documents

Revision ID: c7d2a4f8e6b1
Revises: 8a1c4f6b2d3e
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2a4f8e6b1'
down_revision: Union[str, None] = '8a1c4f6b2d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('chapter_breakdown', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'chapter_breakdown')
