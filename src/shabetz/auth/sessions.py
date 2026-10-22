"""Server-side session lifecycle.

Sessions are rows rather than self-contained tokens so that revoking a session
or changing a role takes effect on the very next request.  For an application
whose entire purpose is controlling who may change configuration, an admin
right that outlives its revocation is the wrong failure mode.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from ..db.base import utcnow
from ..db.models import Session as SessionRow
from ..db.models import User

TOKEN_BYTES = 32


def session_key(token: str) -> str:
    """The row id for a cookie's token. Only the hash is ever stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: DbSession, user: User, ttl_hours: int, user_agent: str | None = None
) -> tuple[SessionRow, str]:
    """A new session row, and the token that goes in the visitor's cookie."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    row = SessionRow(
        id=session_key(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(TOKEN_BYTES),
        expires_at=utcnow() + timedelta(hours=ttl_hours),
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(row)
    db.flush()
    return row, token


def load_valid_session(db: DbSession, token: str) -> SessionRow | None:
    row = db.get(SessionRow, session_key(token))
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at <= utcnow():
        return None
    if not row.user.is_active:
        return None
    return row


def revoke(db: DbSession, session_key_: str) -> None:
    """End one session, by its row id (the hash, not the cookie's token)."""
    row = db.get(SessionRow, session_key_)
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


def purge_stale(db: DbSession, *, keep_days: int = 30) -> int:
    """Delete sessions that ended more than ``keep_days`` ago.

    Expired and revoked rows are useless after that and would otherwise pile
    up forever, one per sign-in.
    """
    cutoff = utcnow() - timedelta(days=keep_days)
    result = db.execute(
        delete(SessionRow).where(
            (SessionRow.expires_at < cutoff)
            | (SessionRow.revoked_at.is_not(None) & (SessionRow.revoked_at < cutoff))
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
