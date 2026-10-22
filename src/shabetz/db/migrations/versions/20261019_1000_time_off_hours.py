"""part-day time off

Revision ID: c63f9b2e5d48
Revises: b52e8a1d4c37
Create Date: 2026-10-19 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c63f9b2e5d48"
down_revision = "b52e8a1d4c37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("time_off") as batch:
        batch.add_column(sa.Column("start_hour", sa.Float(), nullable=True))
        batch.add_column(sa.Column("end_hour", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("time_off") as batch:
        batch.drop_column("end_hour")
        batch.drop_column("start_hour")
