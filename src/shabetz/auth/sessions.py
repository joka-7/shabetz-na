"""Server-side session lifecycle.

Sessions are rows rather than self-contained tokens so that revoking a session
or changing a role takes effect on the very next request.  For an application
whose entire purpose is controlling who may change configuration, an admin
right that outlives its revocation is the wrong failure mode.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db.base import utcnow
from ..db.models import Session as SessionRow
from ..db.models import User

TOKEN_BYTES = 32


def create_session(
    db: DbSession, user: User, ttl_hours: int, user_agent: str | None = None
) -> SessionRow:
    row = SessionRow(
        id=secrets.token_urlsafe(TOKEN_BYTES),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(TOKEN_BYTES),
        expires_at=utcnow() + timedelta(hours=ttl_hours),
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(row)
    db.flush()
    return row


def load_valid_session(db: DbSession, session_id: str) -> SessionRow | None:
    row = db.get(SessionRow, session_id)
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at <= utcnow():
        return None
    if not row.user.is_active:
        return None
    return row


def revoke(db: DbSession, session_id: str) -> None:
    row = db.get(SessionRow, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()


def revoke_all_for_user(db: DbSession, user_id: int) -> int:
    rows = db.scalars(
        select(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
    ).all()
    now = utcnow()
    for row in rows:
        row.revoked_at = now
    return len(rows)
