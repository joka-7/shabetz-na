"""schedule publishing: a draft is private to editors until it is published

Revision ID: 8c2e4a61f0b7
Revises: 5b1f0c7e2a94
Create Date: 2026-09-30 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "8c2e4a61f0b7"
down_revision = "5b1f0c7e2a94"
branch_labels = None
depends_on = None


def _dt() -> sa.types.TypeEngine:
    return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    with op.batch_alter_table("schedule_runs") as batch:
        batch.add_column(sa.Column("published_at", _dt(), nullable=True))
        batch.add_column(sa.Column("published_by", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_schedule_runs_published_by", "users", ["published_by"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("schedule_runs") as batch:
        batch.drop_constraint("fk_schedule_runs_published_by", type_="foreignkey")
        batch.drop_column("published_by")
        batch.drop_column("published_at")
