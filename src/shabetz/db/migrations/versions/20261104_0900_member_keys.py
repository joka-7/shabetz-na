"""end-to-end encryption: each account's wrapped key pair

Revision ID: c8e4b1f0a2d6
Revises: 9d1f3a7c5b84
Create Date: 2026-11-04 09:00:00

The first table of docs/E2EE-DESIGN.md. It holds only what the browser uploads:
a public key and two wrapped copies of the secret key, never the key itself.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "c8e4b1f0a2d6"
down_revision = "9d1f3a7c5b84"
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
        "member_keys",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("wrapped_sk_passphrase", sa.String(255), nullable=False),
        sa.Column("wrapped_sk_recovery", sa.String(255), nullable=False),
        sa.Column("kdf_salt", sa.String(64), nullable=False),
        sa.Column("kdf_opslimit", sa.Integer(), nullable=False),
        sa.Column("kdf_memlimit", sa.Integer(), nullable=False),
        sa.Column("previous_wraps", sa.JSON(), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("updated_at", _dt(), nullable=False),
        **MYSQL,
    )


def downgrade() -> None:
    op.drop_table("member_keys")
