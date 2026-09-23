"""Sign-in, sign-out and first-run bootstrap."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth import google, recovery
from ...auth import service as auth_service
from ...auth.passwords import WeakPassword, validate_password
from ...auth.recovery import RecoveryCodes
from ...auth.sessions import create_session, revoke
from ...auth.throttle import FailureThrottle
from ...config import Settings
from ...db.models import User
from ...domain.enums import UserRole
from ...services.settings_service import load_settings, save_settings
from ..deps import (
    client_address,
    current_user,
    get_db,
    login_throttle,
    recovery_codes,
    require_admin,
    settings_dep,
)
from ..errors import (
    Conflict,
    FeatureUnavailable,
    Forbidden,
    NotFound,
    TooManyRequests,
    Unauthorized,
    UnprocessableConfig,
)
from ..schemas import (
    BootstrapAdminRequest,
    LoginRequest,
    RecoveryCompleteRequest,
    RecoveryStartOut,
    SessionOut,
    UserOut,
)

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
    return {
        # An account exists, so the unauthenticated bootstrap route is closed.
        "setup_complete": auth_service.setup_is_complete(db),
        # The administrator has been through the configuration wizard.
        "wizard_completed": load_settings(db).setup_completed,
    }


@router.post("/setup/complete")
def complete_wizard(db: DbSession = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    """Remember that the wizard is done.

    Without this the wizard reopened every time an administrator reloaded the
    app, which on a desktop app opened daily is every single day.
    """
    settings = load_settings(db)
    if not settings.setup_completed:
        save_settings(db, settings.model_copy(update={"setup_completed": True}))
    return {"wizard_completed": True}


@router.post("/setup/bootstrap-admin", status_code=status.HTTP_201_CREATED)
def bootstrap_admin(
    payload: BootstrapAdminRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    throttle: FailureThrottle = Depends(login_throttle),
) -> SessionOut:
    """Create the first administrator.

    Reachable without authentication only while no account exists; the window
    closes permanently once one does. On a server it also needs the setup code
    printed when the server started: otherwise a freshly deployed site belongs
    to whoever happens to load it first.
    """
    address = client_address(request)
    if throttle.is_blocked(address):
        raise TooManyRequests(throttle.retry_after_seconds(address))

    if settings.setup_token_required:
        if not settings.setup_token:
            # Fail closed: a production server with no code configured must not
            # fall back to letting anyone claim it.
            raise FeatureUnavailable(
                "No setup code is configured. Start the server with 'shabetz serve', "
                "which prints one, or set SHABETZ_SETUP_TOKEN."
            )
        supplied = (payload.setup_code or "").strip().upper()
        if not secrets.compare_digest(supplied, settings.setup_token.strip().upper()):
            throttle.record_failure(address)
            raise Forbidden("Incorrect setup code")

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
    throttle: FailureThrottle = Depends(login_throttle),
) -> SessionOut:
    # Checked before the password is verified, so a blocked address's guesses
    # never reach the account's own lockout counter.
    address = client_address(request)
    if throttle.is_blocked(address):
        raise TooManyRequests(throttle.retry_after_seconds(address))

    try:
        user = auth_service.authenticate_password(
            db,
            payload.email,
            payload.password,
            max_attempts=settings.login_max_attempts,
            lockout_minutes=settings.login_lockout_minutes,
        )
    except auth_service.AccountLocked as exc:
        throttle.record_failure(address)
        raise Forbidden(str(exc)) from exc
    except auth_service.AuthError as exc:
        # Not reset on success: otherwise signing in to one's own account
        # between guesses would clear the record.
        throttle.record_failure(address)
        raise Unauthorized("Invalid email or password") from exc

    return _issue_session(response, db, user, settings, request)


# ------------------------------------------------------- desktop password reset


@router.post("/auth/recovery/start", response_model=RecoveryStartOut)
def start_recovery(
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    codes: RecoveryCodes = Depends(recovery_codes),
) -> RecoveryStartOut:
    """Write a one-time reset code into the desktop app's own folder.

    Only the desktop app offers this: being able to open that folder is being
    the person the data belongs to. A hosted server answers as if the route did
    not exist.
    """
    if not settings.password_recovery_enabled:
        raise NotFound()
    directory = Path(settings.data_dir)
    admins = db.scalars(
        select(User.email)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .order_by(User.email)
    ).all()
    path = recovery.write_code_file(directory, codes.issue(), list(admins))
    recovery.open_for_user(path)
    return RecoveryStartOut(file_path=str(path))


@router.post("/auth/recovery/complete")
def complete_recovery(
    payload: RecoveryCompleteRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    codes: RecoveryCodes = Depends(recovery_codes),
) -> SessionOut:
    """Set a new password with the code from the file, and sign in."""
    if not settings.password_recovery_enabled:
        raise NotFound()
    # Checked first, so a too-short password does not spend the code.
    try:
        validate_password(payload.password)
    except WeakPassword as exc:
        raise UnprocessableConfig(str(exc)) from exc

    # Checked before the code too. Saying whether an account exists is harmless
    # here: the code file lists the administrators anyway.
    user = auth_service.find_active_user_by_email(db, payload.email)
    if user is None:
        raise UnprocessableConfig("No account uses that email address")
    if not codes.redeem(payload.code):
        raise Forbidden("Incorrect or expired reset code")

    auth_service.set_password(db, user, payload.password)
    user.failed_login_count = 0
    user.locked_until = None
    recovery.remove_code_file(Path(settings.data_dir))
    # Whatever tripped the address throttle on the way here is resolved now.
    throttle = getattr(request.app.state, "login_throttle", None)
    if throttle is not None:
        throttle.clear(client_address(request))
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


# --------------------------------------------------------------- Google sign-in


def _require_google(settings: Settings) -> None:
    """Absent credentials mean the feature does not exist, not that it failed."""
    if not settings.google_enabled:
        raise NotFound("Google sign-in is not configured")


@router.get("/auth/google/authorize")
def google_authorize(settings: Settings = Depends(settings_dep)) -> RedirectResponse:
    _require_google(settings)
    url, state_cookie = google.begin(
        client_id=settings.google_client_id,
        redirect_uri=settings.google_redirect_uri,
        secret_key=settings.resolved_secret_key(),
    )
    redirect = RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    redirect.set_cookie(
        google.STATE_COOKIE,
        state_cookie,
        httponly=True,
        secure=settings.cookie_secure,
        # Lax suffices: Google returns with a top-level GET navigation, which
        # Lax cookies accompany. None would only widen where it is sent.
        samesite="lax",
        max_age=google.STATE_MAX_AGE_SECONDS,
        path="/",
    )
    return redirect


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> RedirectResponse:
    _require_google(settings)

    if error or not code:
        return _google_failure("cancelled")

    try:
        identity = await google.complete(
            code=code,
            state=state,
            cookie_value=request.cookies.get(google.STATE_COOKIE),
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
            secret_key=settings.resolved_secret_key(),
        )
    except google.GoogleAuthError:
        return _google_failure("failed")

    try:
        # Sign-in only: an identity with no invited account is refused rather
        # than being allowed to create one.
        user = auth_service.authenticate_google(
            db, google_sub=identity.subject, email=identity.email
        )
    except auth_service.AuthError:
        return _google_failure("no-account")

    redirect = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    session_row = create_session(
        db, user, settings.session_ttl_hours, request.headers.get("user-agent")
    )
    redirect.set_cookie(
        settings.cookie_name,
        session_row.id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    # The CSRF token has to reach JavaScript, so unlike the session it is set
    # readable; it is useless without the HttpOnly session cookie.
    redirect.set_cookie(
        settings.csrf_cookie_name,
        session_row.csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    redirect.delete_cookie(google.STATE_COOKIE, path="/")
    return redirect


def _google_failure(reason: str) -> RedirectResponse:
    redirect = RedirectResponse(f"/?auth_error={reason}", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(google.STATE_COOKIE, path="/")
    return redirect
