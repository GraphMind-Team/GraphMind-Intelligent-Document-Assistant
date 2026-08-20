"""add email_verified_at to users

Revision ID: 21fe494be69e
Revises: a6c5923523fa
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21fe494be69e'
down_revision: Union[str, None] = 'a6c5923523fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, no server_default (unlike theme's migration) -- NULL is a
    # real, meaningful state here ("never verified"), not a placeholder
    # waiting on a backfill the way content_hash's staged migration was.
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))

    # Story 1.6 turns on a hard login block for unverified accounts
    # (REQUIRE_EMAIL_VERIFICATION defaults to true). Without this backfill,
    # every account that existed before this migration -- including the
    # two permanent QA accounts scripts/isolation_proof.py and
    # scripts/eval_harness.py log in as -- would be locked out on their
    # next login. Grandfathering them in as "verified since account
    # creation" is a deliberate one-time exception for pre-1.6 rows only;
    # every row created after this migration starts NULL and must go
    # through the real verify-email flow.
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")


def downgrade() -> None:
    op.drop_column('users', 'email_verified_at')
