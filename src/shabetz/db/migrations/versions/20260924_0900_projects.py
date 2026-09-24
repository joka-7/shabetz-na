"""projects: separate workspaces, per-project roles, invite links

Everything an organisation configures now belongs to a project, and roles move
from the account to project membership, so one account can administer one
project and be staff in another.

An existing installation keeps working: if the database already holds data, it
becomes the first project, named after the configured organisation, and every
account becomes a member with the role it had (SCHEDULER is now COLLABORATOR).

Types are written inline, as in the initial revision, so this stays a fixed
snapshot however the models change later.

Revision ID: 5b1f0c7e2a94
Revises: d847382b09ed
Create Date: 2026-09-24 09:00:00
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "5b1f0c7e2a94"
down_revision = "d847382b09ed"
branch_labels = None
depends_on = None

MYSQL: dict[str, Any] = {
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
    "mysql_engine": "InnoDB",
}


def _dt() -> sa.types.TypeEngine:
    return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


# Tables whose rows belong to exactly one project.
SCOPED = [
    "divisions",
    "proficiency_levels",
    "skills",
    "shift_templates",
    "jobs",
    "people",
    "time_off",
    "schedule_runs",
]

# Old single-organisation uniques and their per-project replacements.
UNIQUES = [
    ("divisions", "uq_divisions_name", ["name"], "uq_divisions_project_id", ["project_id", "name"]),
    ("skills", "uq_skills_name", ["name"], "uq_skills_project_id", ["project_id", "name"]),
    (
        "proficiency_levels",
        "uq_proficiency_levels_rank",
        ["rank"],
        "uq_proficiency_levels_project_id",
        ["project_id", "rank"],
    ),
]

ROLE_FROM_USER = {"ADMIN": "ADMIN", "SCHEDULER": "COLLABORATOR", "STAFF": "STAFF"}


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_projects_created_by", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        **MYSQL,
    )
    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_members_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_project_members_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_project_members_person_id", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_members"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_id"),
        **MYSQL,
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    op.create_table(
        "project_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("single_use", sa.Boolean(), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("expires_at", _dt(), nullable=False),
        sa.Column("revoked_at", _dt(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_invites_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_project_invites_person_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_project_invites_created_by", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_invites"),
        sa.UniqueConstraint("token_hash", name="uq_project_invites_token_hash"),
        **MYSQL,
    )
    op.create_index("ix_project_invites_project_id", "project_invites", ["project_id"])

    for table in [*SCOPED, "audit_log"]:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))

    project_id = _move_existing_data_into_first_project()

    for table in SCOPED:
        if project_id is not None:
            op.execute(sa.text(f"UPDATE {table} SET project_id = :p").bindparams(p=project_id))
        with op.batch_alter_table(table) as batch:
            batch.alter_column("project_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_project_id", "projects", ["project_id"], ["id"], ondelete="CASCADE"
            )
            batch.create_index(f"ix_{table}_project_id", ["project_id"])
    if project_id is not None:
        op.execute(sa.text("UPDATE audit_log SET project_id = :p").bindparams(p=project_id))
    with op.batch_alter_table("audit_log") as batch:
        batch.create_foreign_key(
            "fk_audit_log_project_id", "projects", ["project_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_audit_log_project_id", ["project_id"])

    for table, old_name, _, new_name, new_cols in UNIQUES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(old_name, type_="unique")
            batch.create_unique_constraint(new_name, new_cols)

    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_person_id", type_="foreignkey")
        batch.drop_constraint("uq_users_google_sub", type_="unique")
        batch.drop_column("person_id")
        batch.drop_column("role")
        batch.drop_column("google_sub")
        batch.add_column(sa.Column("firebase_uid", sa.String(length=255), nullable=True))
        batch.create_unique_constraint("uq_users_firebase_uid", ["firebase_uid"])

    op.drop_table("settings")


def _move_existing_data_into_first_project() -> int | None:
    """Create project #1 from an existing installation, if there is one."""
    conn = op.get_bind()
    has_data = any(
        conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        for table in ("users", "divisions", "people", "jobs")
    )
    if not has_data:
        return None

    # Built rather than written as text: "key" is a reserved word in MySQL.
    settings_table = sa.table("settings", sa.column("key", sa.String), sa.column("value_json"))
    settings_row = conn.execute(
        sa.select(settings_table.c.value_json).where(settings_table.c.key == "scheduling")
    ).first()
    settings = _as_dict(settings_row[0]) if settings_row else {}
    name = (settings.get("organization_name") or "").strip() or "My organization"

    projects = sa.table(
        "projects",
        sa.column("name", sa.String),
        sa.column("settings_json", sa.JSON),
        sa.column("created_at", sa.DateTime),
    )
    conn.execute(
        projects.insert().values(name=name[:120], settings_json=settings or None, created_at=_now())
    )
    project_id = conn.execute(sa.text("SELECT MAX(id) FROM projects")).scalar()

    members = sa.table(
        "project_members",
        sa.column("project_id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("role", sa.String),
        sa.column("person_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
    )
    for user_id, role, person_id in conn.execute(
        sa.text("SELECT id, role, person_id FROM users")
    ).all():
        conn.execute(
            members.insert().values(
                project_id=project_id,
                user_id=user_id,
                role=ROLE_FROM_USER.get(role, "STAFF"),
                person_id=person_id,
                created_at=_now(),
            )
        )
    assert project_id is not None
    return int(project_id)


def _now() -> datetime:
    # Naive UTC, as the application stores it in every dialect.
    return datetime.now(UTC).replace(tzinfo=None)


def _as_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):  # SQLite and MySQL may hand JSON back as text
        import json

        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


def downgrade() -> None:
    """Back to one organisation. Only possible with at most one project."""
    conn = op.get_bind()
    if (conn.execute(sa.text("SELECT COUNT(*) FROM projects")).scalar() or 0) > 1:
        raise RuntimeError("Cannot downgrade: more than one project exists")

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("key", name="pk_settings"),
        **MYSQL,
    )
    first = conn.execute(sa.text("SELECT settings_json FROM projects")).first()
    if first and first[0] is not None:
        settings = sa.table(
            "settings", sa.column("key", sa.String), sa.column("value_json", sa.JSON)
        )
        conn.execute(settings.insert().values(key="scheduling", value_json=_as_dict(first[0])))

    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_firebase_uid", type_="unique")
        batch.drop_column("firebase_uid")
        batch.add_column(sa.Column("google_sub", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("role", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("person_id", sa.Integer(), nullable=True))
    for user_id, role, person_id in conn.execute(
        sa.text("SELECT user_id, role, person_id FROM project_members")
    ).all():
        old_role = {"COLLABORATOR": "SCHEDULER"}.get(role, role)
        conn.execute(
            sa.text("UPDATE users SET role = :r, person_id = :p WHERE id = :u").bindparams(
                r=old_role, p=person_id, u=user_id
            )
        )
    conn.execute(sa.text("UPDATE users SET role = 'STAFF' WHERE role IS NULL"))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("role", existing_type=sa.String(length=20), nullable=False)
        batch.create_unique_constraint("uq_users_google_sub", ["google_sub"])
        batch.create_foreign_key(
            "fk_users_person_id", "people", ["person_id"], ["id"], ondelete="SET NULL"
        )

    for table, old_name, old_cols, new_name, _ in UNIQUES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(new_name, type_="unique")
            batch.create_unique_constraint(old_name, old_cols)

    for table in [*SCOPED, "audit_log"]:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_project_id", type_="foreignkey")
            batch.drop_index(f"ix_{table}_project_id")
            batch.drop_column("project_id")

    op.drop_table("project_invites")
    op.drop_table("project_members")
    op.drop_table("projects")
