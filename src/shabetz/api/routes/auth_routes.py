"""Sign-in, sign-out and first-run bootstrap."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from ...auth import service as auth_service
from ...auth.passwords import WeakPassword
from ...auth.sessions import create_session, revoke
from ...config import Settings
from ...db.models import User
from ..deps import current_user, get_db, settings_dep
from ..errors import Conflict, Forbidden, Unauthorized, UnprocessableConfig
from ..schemas import BootstrapAdminRequest, LoginRequest, SessionOut, UserOut

router = APIRouter(prefix="/api", tags=["auth"])


def _issue_session(
    response: Response, db: DbSession, user: User, settings: Settings, request: Request
) -> SessionOut:
    session_row = create_session(
        db, user, settings.session_ttl_hours, request.headers.get("user-agent")
    )
    response.set_cookie(
        settings.cookie_name,
        session_row.id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session_row.csrf_token)


@router.get("/setup/status")
def setup_status(db: DbSession = Depends(get_db)) -> dict:
    return {"setup_complete": auth_service.setup_is_complete(db)}


@router.post("/setup/bootstrap-admin", status_code=status.HTTP_201_CREATED)
def bootstrap_admin(
    payload: BootstrapAdminRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> SessionOut:
    """Create the first administrator.

    Reachable without authentication only while no account exists; the window
    closes permanently once one does.
    """
    try:
        user = auth_service.bootstrap_first_admin(
            db,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
        )
    except WeakPassword as exc:
        raise UnprocessableConfig(str(exc)) from exc
    except auth_service.AuthError as exc:
        raise Conflict(str(exc)) from exc

    return _issue_session(response, db, user, settings, request)


@router.post("/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> SessionOut:
    try:
        user = auth_service.authenticate_password(
            db,
            payload.email,
            payload.password,
            max_attempts=settings.login_max_attempts,
            lockout_minutes=settings.login_lockout_minutes,
        )
    except auth_service.AccountLocked as exc:
        raise Forbidden(str(exc)) from exc
    except auth_service.AuthError as exc:
        raise Unauthorized("Invalid email or password") from exc

    return _issue_session(response, db, user, settings, request)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    user: User = Depends(current_user),
) -> dict:
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        revoke(db, session_id)
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.model_validate(user)
