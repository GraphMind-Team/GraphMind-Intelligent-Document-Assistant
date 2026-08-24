"""add chat_sessions table and chat_messages.session_id

Revision ID: c8d3f5a1b7e9
Revises: f3a8b6c1d9e4
Create Date: 2026-08-24 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d3f5a1b7e9'
down_revision: Union[str, None] = 'f3a8b6c1d9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Both halves land in one migration (mirrors f3a8c1d9b6e2's folders
    # table + documents.folder_id) -- the FK below has nothing to point at
    # otherwise.
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_chat_sessions_user_id_updated_at', 'chat_sessions', ['user_id', 'updated_at'], unique=False
    )

    # Added nullable first specifically so the backfill step below doesn't
    # violate a NOT NULL constraint mid-migration (mirrors
    # e1f5c8a2b4d7's content_hash backfill).
    op.add_column('chat_messages', sa.Column('session_id', sa.Uuid(), nullable=True))

    # Backfill: every existing user's pre-migration messages all belonged
    # to one implicit conversation (the old FR-17 model) -- give each such
    # user exactly one ChatSession spanning their existing rows, so no
    # history is lost or split. `created_at`/`updated_at` bracket that
    # user's real message timestamps rather than defaulting to "now",
    # so the backfilled session doesn't look like it was just created.
    connection = op.get_bind()
    chat_messages = sa.table(
        'chat_messages',
        sa.column('id', sa.Uuid()),
        sa.column('user_id', sa.Uuid()),
        sa.column('session_id', sa.Uuid()),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )
    chat_sessions = sa.table(
        'chat_sessions',
        sa.column('id', sa.Uuid()),
        sa.column('user_id', sa.Uuid()),
        sa.column('title', sa.String()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    per_user_bounds = connection.execute(
        sa.select(
            chat_messages.c.user_id,
            sa.func.min(chat_messages.c.created_at).label('first_created_at'),
            sa.func.max(chat_messages.c.created_at).label('last_created_at'),
        ).group_by(chat_messages.c.user_id)
    ).fetchall()
    for row in per_user_bounds:
        session_id = uuid.uuid4()
        connection.execute(
            chat_sessions.insert().values(
                id=session_id,
                user_id=row.user_id,
                title=None,
                created_at=row.first_created_at,
                updated_at=row.last_created_at,
            )
        )
        connection.execute(
            chat_messages.update()
            .where(chat_messages.c.user_id == row.user_id)
            .values(session_id=session_id)
        )

    op.alter_column('chat_messages', 'session_id', existing_type=sa.Uuid(), nullable=False)
    op.create_foreign_key(
        'fk_chat_messages_session_id_chat_sessions', 'chat_messages', 'chat_sessions', ['session_id'], ['id'],
    )

    op.drop_index('ix_chat_messages_user_id_created_at_role_id', table_name='chat_messages')
    op.create_index(
        'ix_chat_messages_session_id_created_at_role_id',
        'chat_messages',
        ['session_id', 'created_at', 'role', 'id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_chat_messages_session_id_created_at_role_id', table_name='chat_messages')
    op.create_index(
        'ix_chat_messages_user_id_created_at_role_id',
        'chat_messages',
        ['user_id', 'created_at', 'role', 'id'],
        unique=False,
    )
    op.drop_constraint('fk_chat_messages_session_id_chat_sessions', 'chat_messages', type_='foreignkey')
    op.drop_column('chat_messages', 'session_id')
    op.drop_index('ix_chat_sessions_user_id_updated_at', table_name='chat_sessions')
    op.drop_table('chat_sessions')
