"""Alembic environment, wired to `app.shared.models.Base.metadata`.

Reads `DATABASE_URL` from the environment (via `.env` in local dev) rather
than from a committed `sqlalchemy.url` in alembic.ini, so no connection
string is ever hardcoded or committed (AD-8).

No models are declared yet (Story 1.1 is the skeleton; `users` arrives in
Story 1.3), so `target_metadata` currently has no tables -- autogenerate
will start producing real migrations once models exist.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Make `app` importable when alembic is run from `backend/`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.shared.models import Base  # noqa: E402

load_dotenv()

# this is the Alembic Config object, which provides access to values within
# the .ini file in use.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL", "").strip()
if not database_url:
    raise RuntimeError(
        "Missing required environment variable: DATABASE_URL. See backend/.env.example."
    )
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
