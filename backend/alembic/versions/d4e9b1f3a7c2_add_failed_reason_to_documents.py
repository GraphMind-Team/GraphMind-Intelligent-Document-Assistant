"""add failed_reason to documents

Revision ID: d4e9b1f3a7c2
Revises: c7d2a4f8e6b1
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e9b1f3a7c2'
down_revision: Union[str, None] = 'c7d2a4f8e6b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('failed_reason', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'failed_reason')
