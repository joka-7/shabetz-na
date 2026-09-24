"""Upgrading an existing single-organisation database to projects.

The desktop app upgrades its users' own data files in place, and a hosted site
may already have an administrator and a roster, so the move to projects must
carry everything across rather than start empty.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import column, create_engine, table, text

from shabetz.config import normalize_database_url
from shabetz.db.migrate import MIGRATIONS_DIR

BEFORE_PROJECTS = "d847382b09ed"


def _config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    return config


# CI points this at an empty MySQL or PostgreSQL database, so the move of
# real rows is proven on each server the app supports, not only SQLite.
MIGRATION_TEST_URL = os.environ.get("SHABETZ_TEST_MIGRATION_URL", "")


@pytest.fixture
def url(tmp_path: Path) -> str:
    if not MIGRATION_TEST_URL:
        return f"sqlite:///{tmp_path / 'old.db'}"
    # A shared server database: start each test from nothing.
    url = normalize_database_url(MIGRATION_TEST_URL)
    command.downgrade(_config(url), "base")
    return url


def _seed_old_schema(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO divisions (id, name, display_order, is_active) "
                "VALUES (1, 'North', 0, TRUE)"
            )
        )
        db.execute(
            text(
                "INSERT INTO people (id, full_name, division_id, is_active) "
                "VALUES (7, 'Dana', 1, TRUE)"
            )
        )
        for uid, email, role, person in [
            (1, "admin@example.com", "ADMIN", None),
            (2, "sched@example.com", "SCHEDULER", None),
            (3, "staff@example.com", "STAFF", 7),
        ]:
            db.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, full_name, role, is_active, "
                    "person_id, failed_login_count, created_at) "
                    "VALUES (:id, :email, 'x', 'Name', :role, TRUE, :person, 0, "
                    "'2026-01-01 00:00:00')"
                ),
                {"id": uid, "email": email, "role": role, "person": person},
            )
        # Built rather than written as text: "key" is a reserved word in MySQL.
        settings = table("settings", column("key"), column("value_json"))
        db.execute(
            settings.insert().values(
                key="scheduling",
                value_json=json.dumps(
                    {"organization_name": "Acme Security", "rest_period_hours": 10}
                ),
            )
        )
        db.execute(
            text(
                "INSERT INTO time_off (id, person_id, start_date, end_date, status, created_at) "
                "VALUES (1, 7, '2026-02-01', '2026-02-02', 'APPROVED', '2026-01-01 00:00:00')"
            )
        )
        db.execute(
            text(
                "INSERT INTO schedule_runs (id, params_json, summary_json, payload_gz, created_at) "
                "VALUES ('run1', '{}', '{}', :blob, '2026-01-01 00:00:00')"
            ),
            {"blob": b"\x00"},
        )
    engine.dispose()


def test_an_existing_installation_becomes_the_first_project(url: str) -> None:
    command.upgrade(_config(url), BEFORE_PROJECTS)
    _seed_old_schema(url)

    command.upgrade(_config(url), "head")

    engine = create_engine(url)
    with engine.connect() as db:
        projects = db.execute(text("SELECT id, name, settings_json FROM projects")).all()
        assert len(projects) == 1
        project_id, name, settings = projects[0]
        assert name == "Acme Security"
        settings = settings if isinstance(settings, dict) else json.loads(settings)
        assert settings["rest_period_hours"] == 10

        members = db.execute(
            text("SELECT user_id, role, person_id FROM project_members ORDER BY user_id")
        ).all()
        # SCHEDULER is now COLLABORATOR; the staff account keeps its person.
        assert members == [(1, "ADMIN", None), (2, "COLLABORATOR", None), (3, "STAFF", 7)]

        for table in ("divisions", "people", "time_off", "schedule_runs"):
            assert (
                db.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE project_id = :p"), {"p": project_id}
                ).scalar()
                == 1
            ), table
    engine.dispose()


def test_an_empty_database_gets_no_project(url: str) -> None:
    command.upgrade(_config(url), "head")
    engine = create_engine(url)
    with engine.connect() as db:
        assert db.execute(text("SELECT COUNT(*) FROM projects")).scalar() == 0
    engine.dispose()


def test_the_upgrade_can_be_rolled_back(url: str) -> None:
    command.upgrade(_config(url), BEFORE_PROJECTS)
    _seed_old_schema(url)
    command.upgrade(_config(url), "head")

    command.downgrade(_config(url), BEFORE_PROJECTS)

    engine = create_engine(url)
    with engine.connect() as db:
        roles = db.execute(text("SELECT id, role, person_id FROM users ORDER BY id")).all()
        assert roles == [(1, "ADMIN", None), (2, "SCHEDULER", None), (3, "STAFF", 7)]
        value = db.execute(text("SELECT value_json FROM settings")).scalar()
        value = value if isinstance(value, dict) else json.loads(value)
        assert value["organization_name"] == "Acme Security"
    engine.dispose()
