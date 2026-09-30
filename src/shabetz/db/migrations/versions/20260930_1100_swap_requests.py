"""swap requests: hand a published shift to a colleague, with manager approval

Revision ID: a41d7f3c9e20
Revises: 8c2e4a61f0b7
Create Date: 2026-09-30 11:00:00
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "a41d7f3c9e20"
down_revision = "8c2e4a61f0b7"
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
        "swap_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schedule_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("calendar_date", sa.Date(), nullable=False),
        sa.Column("job_name", sa.String(160), nullable=False),
        sa.Column("template_name", sa.String(120), nullable=False),
        sa.Column(
            "from_person_id",
            sa.Integer(),
            sa.ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_person_id",
            sa.Integer(),
            sa.ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "requested_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", _dt(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        **MYSQL,
    )
    op.create_index("ix_swap_requests_project_id", "swap_requests", ["project_id"])
    op.create_index("ix_swap_project_status", "swap_requests", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_swap_project_status", table_name="swap_requests")
    op.drop_index("ix_swap_requests_project_id", table_name="swap_requests")
    op.drop_table("swap_requests")
