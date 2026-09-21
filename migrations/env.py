"""Alembic environment.

The URL comes from `FLYWHEEL_DATABASE_URL`, the same switch the application
reads, so `alembic upgrade head` always targets the database the app will
actually use -- there is no second place to configure a connection.

`render_as_batch` is on because SQLite cannot ALTER a column in place; batch
mode rebuilds the table around the change instead. Without it, any migration
touching an existing column fails on the SQLite path the course demo uses.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import database_url  # noqa: E402
from storage.models import Base  # noqa: E402

config = context.config
config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _is_sqlite() -> bool:
    return database_url().startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_is_sqlite(),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
