"""add feedback to chat_messages

Revision ID: f332c4553450
Revises: c8d3f5a1b7e9
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f332c4553450'
down_revision: Union[str, None] = 'c8d3f5a1b7e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_messages', sa.Column('feedback', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('chat_messages', 'feedback')
