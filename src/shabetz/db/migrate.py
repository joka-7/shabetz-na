"""Programmatic migrations.

A desktop user cannot run a migration command, so the application upgrades its
own database on launch. The scripts are located relative to this module, which
keeps working when the package is frozen into an executable.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(_config(database_url), "head")
