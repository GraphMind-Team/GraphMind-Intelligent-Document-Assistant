"""Shared SQLAlchemy declarative base.

`Base` is the single declarative base all ORM models attach to, and
`backend/alembic/env.py` points its autogenerate target metadata at
`Base.metadata`. No models are declared yet in Story 1.1 (running project
skeleton) -- the `users` table arrives in Story 1.3's migration.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""
