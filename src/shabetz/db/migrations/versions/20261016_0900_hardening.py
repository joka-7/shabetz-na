"""hardening: schedule edit versions, hashed session ids, a session expiry index

Revision ID: 3e9b6d2c7f15
Revises: a41d7f3c9e20
Create Date: 2026-10-16 09:00:00

Session ids become the SHA-256 of the cookie's token, so a copy of the
database no longer holds working sessions. Existing rows are hashed in place,
so nobody is signed out by the upgrade. A hash cannot be turned back into its
token, so downgrading ends every session instead.
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from alembic import op

revision = "3e9b6d2c7f15"
down_revision = "a41d7f3c9e20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_runs",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    sessions = sa.table("sessions", sa.column("id", sa.String(64)))
    bind = op.get_bind()
    for (token,) in bind.execute(sa.select(sessions.c.id)).fetchall():
        bind.execute(
            sessions.update()
            .where(sessions.c.id == token)
            .values(id=hashlib.sha256(token.encode()).hexdigest())
        )

    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.execute("DELETE FROM sessions")
    with op.batch_alter_table("schedule_runs") as batch:
        batch.drop_column("version")
