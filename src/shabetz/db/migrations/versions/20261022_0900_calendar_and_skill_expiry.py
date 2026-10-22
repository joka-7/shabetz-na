"""calendar feeds and lapsing skills

Revision ID: 6a0c4f8e1b32
Revises: 3e9b6d2c7f15
Create Date: 2026-10-22 09:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "6a0c4f8e1b32"
down_revision = "3e9b6d2c7f15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("person_skills", sa.Column("expires_on", sa.Date(), nullable=True))
    # Batch mode, because SQLite can only add a constraint by rebuilding the table.
    with op.batch_alter_table("project_members") as batch:
        batch.add_column(sa.Column("calendar_token_hash", sa.String(length=64), nullable=True))
        batch.create_unique_constraint(
            "uq_project_members_calendar_token_hash", ["calendar_token_hash"]
        )


def downgrade() -> None:
    with op.batch_alter_table("project_members") as batch:
        batch.drop_constraint("uq_project_members_calendar_token_hash", type_="unique")
        batch.drop_column("calendar_token_hash")
    with op.batch_alter_table("person_skills") as batch:
        batch.drop_column("expires_on")
