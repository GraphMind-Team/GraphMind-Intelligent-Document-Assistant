"""create folders table and document folder_id

Revision ID: f3a8c1d9b6e2
Revises: 21fe494be69e
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d9b6e2'
down_revision: Union[str, None] = '21fe494be69e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Both halves of the folder-grouping feature land in one migration
    # (the spec's Tasks & Acceptance): the `folders` table and
    # `documents.folder_id` must be atomic for referential integrity --
    # the FK below has nothing to point at otherwise.
    op.create_table(
        'folders',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('color', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_folders_user_id'), 'folders', ['user_id'], unique=False)

    op.add_column('documents', sa.Column('folder_id', sa.Uuid(), nullable=True))
    # ON DELETE SET NULL -- deleting a folder never deletes its documents
    # (the spec's Boundaries); the row survives as unfiled. Enforced at the
    # DB level, not just by application code remembering to clear it.
    op.create_foreign_key(
        'fk_documents_folder_id_folders',
        'documents',
        'folders',
        ['folder_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_documents_folder_id_folders', 'documents', type_='foreignkey')
    op.drop_column('documents', 'folder_id')
    op.drop_index(op.f('ix_folders_user_id'), table_name='folders')
    op.drop_table('folders')
