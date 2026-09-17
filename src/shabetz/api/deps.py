"""Request dependencies: database session, current user, and role gates."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession

from ..auth.sessions import load_valid_session
from ..config import Settings, get_settings
from ..db.models import User
from ..db.session import get_session_factory
from ..domain.enums import UserRole
from .errors import Forbidden, Unauthorized

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_db() -> Iterator[DbSession]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def settings_dep() -> Settings:
    return get_settings()


def current_user(
    request: Request,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> User:
    session_id = request.cookies.get(settings.cookie_name)
    if not session_id:
        raise Unauthorized()

    session_row = load_valid_session(db, session_id)
    if session_row is None:
        raise Unauthorized("Session expired or revoked")

    # Authentication rides on a cookie, so state-changing requests must also
    # present the matching CSRF token from a header the browser will not attach
    # automatically on a cross-site request.
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("x-csrf-token")
        if not supplied or supplied != session_row.csrf_token:
            raise Forbidden("Missing or invalid CSRF token")

    request.state.session_id = session_row.id
    return session_row.user


def require_role(minimum: UserRole):  # type: ignore[no-untyped-def]
    """Gate an endpoint on a minimum role.

    Authorization lives here rather than in the frontend router: the SPA hides
    what a role cannot use, but this is what refuses it.
    """
    from ..auth.rbac import at_least

    def _dependency(user: User = Depends(current_user)) -> User:
        if not at_least(user.role, minimum):
            raise Forbidden(f"Requires {minimum.value} role")
        return user

    return _dependency


require_admin = require_role(UserRole.ADMIN)
require_scheduler = require_role(UserRole.SCHEDULER)
require_staff = require_role(UserRole.STAFF)
