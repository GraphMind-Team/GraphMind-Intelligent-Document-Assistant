"""replace chat_messages user_id index with composite index

Revision ID: a6c5923523fa
Revises: 4eb9644cd73d
Create Date: 2026-08-19 13:03:09.145861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6c5923523fa'
down_revision: Union[str, None] = '4eb9644cd73d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_chat_messages_user_id'), table_name='chat_messages')
    op.create_index('ix_chat_messages_user_id_created_at_role_id', 'chat_messages', ['user_id', 'created_at', 'role', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_chat_messages_user_id_created_at_role_id', table_name='chat_messages')
    op.create_index(op.f('ix_chat_messages_user_id'), 'chat_messages', ['user_id'], unique=False)
