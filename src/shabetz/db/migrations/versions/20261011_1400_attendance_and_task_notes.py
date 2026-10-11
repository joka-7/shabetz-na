"""attendance, and notes on tasks

Revision ID: b52e8a1d4c37
Revises: a41d7f3c9e20
Create Date: 2026-10-11 14:00:00
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "b52e8a1d4c37"
down_revision = "a41d7f3c9e20"
branch_labels = None
depends_on = None

MYSQL: dict[str, Any] = {
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
    "mysql_engine": "InnoDB",
}


def _dt() -> sa.types.TypeEngine:
    return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sa.Integer(),
            sa.ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("calendar_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "marked_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("marked_at", _dt(), nullable=False),
        sa.UniqueConstraint("person_id", "calendar_date", name="uq_attendance_person_id"),
        **MYSQL,
    )
    op.create_index("ix_attendance_project_id", "attendance", ["project_id"])
    op.create_index("ix_attendance_project_date", "attendance", ["project_id", "calendar_date"])

    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("notes")
    op.drop_table("attendance")
