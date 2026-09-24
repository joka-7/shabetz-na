"""Alembic environment.

The URL comes from application settings rather than alembic.ini so there is one
source of truth for where the database lives.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shabetz.config import get_settings, normalize_database_url
from shabetz.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# A URL set programmatically (the desktop launcher knows where its database
# file lives) wins; otherwise fall back to application settings.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
else:
    # A URL passed in directly gets the same driver choice as settings do.
    config.set_main_option(
        "sqlalchemy.url",
        normalize_database_url(config.get_main_option("sqlalchemy.url") or "").replace("%", "%%"),
    )
target_metadata = Base.metadata


def _batch_for(url: str) -> bool:
    """SQLite cannot ALTER most things in place, so migrations must rebuild
    tables there. Without this the first schema change after release would fail
    on every installed desktop copy."""
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or ""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=_batch_for(url),
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
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
