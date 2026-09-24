"""Request dependencies: database session, current user, project membership and role gates."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from ..auth.recovery import RecoveryCodes
from ..auth.sessions import load_valid_session
from ..auth.throttle import FailureThrottle
from ..config import Settings, get_settings
from ..db.models import Project, ProjectMember, User
from ..db.session import get_session_factory
from ..domain.enums import ProjectRole
from .errors import ApiError, Forbidden, NotFound, Unauthorized

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


def client_address(request: Request) -> str:
    """The caller's address.

    Behind a reverse proxy this is only the real client when the server trusts
    the proxy's forwarding headers; ``shabetz serve`` configures that.
    """
    return request.client.host if request.client else "unknown"


def login_throttle(request: Request, settings: Settings = Depends(settings_dep)) -> FailureThrottle:
    # Held on the application rather than at module level, so each app -- and
    # each test -- starts with its own clean record.
    throttle = getattr(request.app.state, "login_throttle", None)
    if throttle is None:
        throttle = FailureThrottle(
            settings.login_ip_max_failures, settings.login_ip_window_minutes * 60
        )
        request.app.state.login_throttle = throttle
    return throttle


def recovery_codes(request: Request) -> RecoveryCodes:
    codes = getattr(request.app.state, "recovery_codes", None)
    if codes is None:
        codes = RecoveryCodes()
        request.app.state.recovery_codes = codes
    return codes


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


@dataclass(frozen=True)
class ProjectContext:
    """Who is asking, in which project, with which role.

    Every route that touches a project's data takes this, and every query it
    runs filters on ``project_id`` -- the membership check here is what keeps
    one organisation's data out of another's reach.
    """

    user: User
    project: Project
    member: ProjectMember

    @property
    def project_id(self) -> int:
        return self.project.id

    @property
    def role(self) -> ProjectRole:
        return self.member.role


def _requested_project_id(request: Request) -> int:
    # A header for API calls; a query parameter for downloads, which are
    # plain navigations that cannot carry custom headers.
    raw = request.headers.get("x-project-id") or request.query_params.get("project") or ""
    if not raw.isdigit():
        raise ApiError("NO_PROJECT", "Choose a project first", 400)
    return int(raw)


def project_member(
    request: Request,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> ProjectContext:
    project_id = _requested_project_id(request)
    member = db.scalar(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        .options(joinedload(ProjectMember.project))
    )
    if member is None:
        # The same answer whether the project exists or not, so ids cannot be
        # probed for other organisations' projects.
        raise NotFound("Project not found")
    return ProjectContext(user=user, project=member.project, member=member)


def require_project_role(minimum: ProjectRole):  # type: ignore[no-untyped-def]
    """Gate an endpoint on a minimum role in the requested project.

    The SPA hides what a role cannot use; this is what refuses it.
    """
    from ..auth.rbac import at_least

    def _dependency(ctx: ProjectContext = Depends(project_member)) -> ProjectContext:
        if not at_least(ctx.role, minimum):
            raise Forbidden(f"Requires the {minimum.value} role in this project")
        return ctx

    return _dependency


require_project_admin = require_project_role(ProjectRole.ADMIN)
require_editor = require_project_role(ProjectRole.COLLABORATOR)
