"""add content_hash to documents

Revision ID: e1f5c8a2b4d7
Revises: d4e9b1f3a7c2
Create Date: 2026-08-14 00:00:00.000001

"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f5c8a2b4d7'
down_revision: Union[str, None] = 'd4e9b1f3a7c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Added nullable first specifically so the backfill step below doesn't
    # violate a NOT NULL constraint mid-migration (Design Notes).
    op.add_column('documents', sa.Column('content_hash', sa.String(length=64), nullable=True))

    # Backfill every existing row by hashing its already-stored `content`
    # column -- `content` is `nullable=False` today, so every row has bytes
    # to hash. Cheap at this project's scale (no pagination needed).
    connection = op.get_bind()
    documents = sa.table(
        'documents',
        sa.column('id', sa.Uuid()),
        sa.column('user_id', sa.Uuid()),
        sa.column('content', sa.LargeBinary()),
        sa.column('content_hash', sa.String(length=64)),
    )
    rows = connection.execute(sa.select(documents.c.id, documents.c.content)).fetchall()
    for row in rows:
        # `content` is `nullable=False` at the model level, so a `None`
        # here "shouldn't" happen -- but hashing it unguarded would raise
        # `TypeError` and abort the whole backfill over one bad row. Cheap
        # defensive fallback, consistent with this codebase's existing
        # "shouldn't happen but the fix is one line" precedent (Story 2.5).
        content_hash = hashlib.sha256(row.content or b"").hexdigest()
        connection.execute(
            documents.update().where(documents.c.id == row.id).values(content_hash=content_hash)
        )

    # Guard against pre-existing `(user_id, content_hash)` collisions
    # before the unique index below -- e.g. two rows with genuinely
    # identical content uploaded under the old, pre-2.6 no-dedupe behavior.
    # Left unguarded, `op.create_index(..., unique=True)` would fail with a
    # raw, confusing driver-level `IntegrityError` instead of a clear
    # message pointing at which rows need a human decision. This migration
    # deliberately does not delete or merge colliding rows itself -- which
    # row to keep is a data decision for a human with the specific ids in
    # hand, not something to resolve silently mid-migration.
    collisions = connection.execute(
        sa.select(
            documents.c.user_id,
            documents.c.content_hash,
            sa.func.count().label("row_count"),
        )
        .group_by(documents.c.user_id, documents.c.content_hash)
        .having(sa.func.count() > 1)
    ).fetchall()
    if collisions:
        colliding_pairs = ", ".join(
            f"(user_id={row.user_id}, content_hash={row.content_hash}, rows={row.row_count})"
            for row in collisions
        )
        raise RuntimeError(
            "Cannot add a unique (user_id, content_hash) index: pre-existing duplicate "
            "documents were found (same user, byte-identical content, uploaded before "
            "Story 2.6's dedupe existed). This must be resolved manually -- decide which "
            "row(s) to keep/merge/delete for each pair below -- before re-running this "
            f"migration: {colliding_pairs}"
        )

    op.alter_column('documents', 'content_hash', existing_type=sa.String(length=64), nullable=False)
    op.create_index(
        'ix_documents_user_id_content_hash', 'documents', ['user_id', 'content_hash'], unique=True
    )


def downgrade() -> None:
    op.drop_index('ix_documents_user_id_content_hash', table_name='documents')
    op.drop_column('documents', 'content_hash')
