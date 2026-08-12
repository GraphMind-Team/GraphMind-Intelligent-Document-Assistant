"""Unit test for `user_scoped_select` (backend/app/shared/data_access/tenancy.py).

Uses a throwaway ORM model rather than `User` (which has no `user_id`
column -- it's the identity table, not per-user tenant data) since no real
per-user Postgres table exists yet; Epic 2/3 add the first ones.
"""

import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.data_access import user_scoped_select
from app.shared.models import Base


class _Note(Base):
    __tablename__ = "test_tenancy_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)


def test_user_scoped_select_only_returns_rows_owned_by_the_given_user_id(db_session):
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    db_session.add_all(
        [
            _Note(user_id=user_a, text="A's note"),
            _Note(user_id=user_b, text="B's note"),
        ]
    )
    db_session.flush()

    rows = db_session.execute(user_scoped_select(_Note, user_a)).scalars().all()

    assert [row.text for row in rows] == ["A's note"]
