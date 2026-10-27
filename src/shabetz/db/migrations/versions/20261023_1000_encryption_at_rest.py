"""room for encrypted personal data, and an email lookup index

Revision ID: 9d1f3a7c5b84
Revises: 6a0c4f8e1b32
Create Date: 2026-10-23 10:00:00

Encrypted values are longer than the plain ones they replace, so the columns that
will hold them are widened; ``users.email_hash`` is the keyed fingerprint an
account is found by while its address is stored encrypted. Nothing is encrypted
here: that happens when ``SHABETZ_DATA_KEY`` is set (``shabetz encrypt-data``).

Going back is refused while any value is still encrypted, because the older
columns are too short for it and the older code could not read it. Run
``shabetz decrypt-data`` first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "9d1f3a7c5b84"
down_revision = "6a0c4f8e1b32"
branch_labels = None
depends_on = None

LONG_TEXT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")

# (table, column, the type it had, nullable) for each text column that now holds ciphertext.
TEXT_COLUMNS = [
    ("users", "full_name", sa.String(120), False),
    ("sessions", "user_agent", sa.String(255), True),
    ("people", "full_name", sa.String(160), False),
    ("people", "external_ref", sa.String(120), True),
]
JSON_COLUMNS = [("audit_log", "before_json"), ("audit_log", "after_json")]
# Already unbounded text; only the way they are read and written changes.
UNCHANGED = [
    ("time_off", "reason"),
    ("time_off", "review_note"),
    ("swap_requests", "note"),
    ("swap_requests", "review_note"),
    ("attendance", "note"),
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "email",
            existing_type=sa.String(255),
            type_=sa.String(512),
            existing_nullable=False,
        )
        batch.add_column(sa.Column("email_hash", sa.String(length=64), nullable=True))
        batch.create_unique_constraint("uq_users_email_hash", ["email_hash"])

    for table, column, old, nullable in TEXT_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column, existing_type=old, type_=sa.Text(), existing_nullable=nullable
            )

    for table, column in JSON_COLUMNS:
        if _is_postgres():
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT USING {column}::text")
        else:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(
                    column, existing_type=sa.JSON(), type_=LONG_TEXT, existing_nullable=True
                )


def _refuse_if_encrypted() -> None:
    bind = op.get_bind()
    columns = [(t, c) for t, c, _, _ in TEXT_COLUMNS] + JSON_COLUMNS + UNCHANGED
    columns.append(("users", "email"))
    for table, column in columns:
        found = bind.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE {column} LIKE 'enc1:%' LIMIT 1")
        ).first()
        if found is not None:
            raise RuntimeError(
                f"{table}.{column} is still encrypted. Run `shabetz decrypt-data` "
                "(with the key set) before downgrading."
            )
    for (payload,) in bind.execute(sa.text("SELECT payload_gz FROM schedule_runs")):
        if bytes(payload[:4]) == b"ENC1":
            raise RuntimeError(
                "Schedules are still encrypted. Run `shabetz decrypt-data` "
                "(with the key set) before downgrading."
            )


def downgrade() -> None:
    _refuse_if_encrypted()

    for table, column in JSON_COLUMNS:
        if _is_postgres():
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSON USING {column}::json")
        else:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(
                    column, existing_type=LONG_TEXT, type_=sa.JSON(), existing_nullable=True
                )

    for table, column, old, nullable in TEXT_COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column, existing_type=sa.Text(), type_=old, existing_nullable=nullable
            )

    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_email_hash", type_="unique")
        batch.drop_column("email_hash")
        batch.alter_column(
            "email",
            existing_type=sa.String(512),
            type_=sa.String(255),
            existing_nullable=False,
        )
