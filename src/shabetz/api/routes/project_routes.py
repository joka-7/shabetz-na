"""Projects, their members, and the invite links that bring members in.

Anyone signed in can create a project and becomes its administrator. An
administrator brings others in by sharing an invite link for a role; the
desktop app, which runs on one computer, adds local accounts with a password
instead and keeps to a single project.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from ...auth import service as auth_service
from ...auth.passwords import WeakPassword
from ...auth.rbac import at_least
from ...config import Settings
from ...db import models as orm
from ...db.base import utcnow
from ...db.models import Project, ProjectInvite, ProjectMember, User
from ...domain.enums import ProjectRole
from ..deps import (
    ProjectContext,
    current_user,
    get_db,
    project_member,
    require_project_admin,
    settings_dep,
)
from ..errors import Conflict, NotFound, UnprocessableConfig
from ..schemas import (
    InviteCreatedOut,
    InviteIn,
    InviteOut,
    InvitePreviewOut,
    LocalMemberCreate,
    MemberOut,
    MemberUpdate,
    PasswordSet,
    ProjectIn,
    ProjectOut,
)

router = APIRouter(prefix="/api", tags=["projects"])

TOKEN_BYTES = 32


def _audit(db: DbSession, ctx: ProjectContext, entity: str, entity_id: object, action: str) -> None:
    db.add(
        orm.AuditLog(
            project_id=ctx.project_id,
            user_id=ctx.user.id,
            entity_type=entity,
            entity_id=str(entity_id),
            action=action,
        )
    )


def _project_out(member: ProjectMember) -> ProjectOut:
    return ProjectOut(
        id=member.project.id,
        name=member.project.name,
        role=member.role,
        person_id=member.person_id,
    )


def _check_person(db: DbSession, ctx: ProjectContext, person_id: int | None) -> None:
    if person_id is None:
        return
    person = db.get(orm.Person, person_id)
    if person is None or person.project_id != ctx.project_id:
        raise UnprocessableConfig(f"Person {person_id} does not exist")


# ------------------------------------------------------------------ projects


@router.get("/projects", response_model=list[ProjectOut])
def my_projects(db: DbSession = Depends(get_db), user: User = Depends(current_user)) -> list:
    members = db.scalars(
        select(ProjectMember)
        .join(Project)
        .where(ProjectMember.user_id == user.id)
        .options(joinedload(ProjectMember.project))
        .order_by(Project.name, Project.id)
    ).all()
    return [_project_out(m) for m in members]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectIn,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(settings_dep),
) -> ProjectOut:
    # The desktop app is one organisation on one computer.
    if settings.deployment == "desktop" and db.scalar(select(Project.id).limit(1)) is not None:
        raise Conflict("The desktop app holds a single project")
    project = auth_service.create_project(db, user, payload.name)
    return _project_out(project.members[0])


@router.put("/project", response_model=ProjectOut)
def rename_project(
    payload: ProjectIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
) -> ProjectOut:
    ctx.project.name = payload.name.strip()
    _audit(db, ctx, "project", ctx.project_id, "rename")
    return _project_out(ctx.member)


@router.delete("/project", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
    settings: Settings = Depends(settings_dep),
) -> None:
    """Delete the project and everything in it, for every member."""
    if settings.deployment == "desktop":
        raise Conflict("The desktop app's project cannot be deleted")
    project_id = ctx.project_id
    db.expunge_all()
    # The database cascades to every row the project owns.
    db.execute(delete(Project).where(Project.id == project_id))


@router.post("/project/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_project(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> None:
    try:
        auth_service.assert_not_last_admin(db, ctx.member)
    except auth_service.LastAdminError as exc:
        raise Conflict(str(exc)) from exc
    db.delete(ctx.member)


# ------------------------------------------------------------------- members


def _member_out(member: ProjectMember) -> MemberOut:
    user = member.user
    return MemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        person_id=member.person_id,
        has_password=bool(user.password_hash),
        has_google=bool(user.firebase_uid),
        last_login_at=user.last_login_at,
        is_locked=bool(user.locked_until and user.locked_until > utcnow()),
    )


def _load_member(db: DbSession, ctx: ProjectContext, member_id: int) -> ProjectMember:
    member = db.get(ProjectMember, member_id)
    if member is None or member.project_id != ctx.project_id:
        raise NotFound("Member not found")
    return member


@router.get("/project/members", response_model=list[MemberOut])
def list_members(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(require_project_admin)
) -> list[MemberOut]:
    members = db.scalars(
        select(ProjectMember)
        .join(User)
        .where(ProjectMember.project_id == ctx.project_id)
        .options(joinedload(ProjectMember.user))
        .order_by(User.email)
    ).all()
    return [_member_out(m) for m in members]


@router.post("/project/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_local_member(
    payload: LocalMemberCreate,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
    settings: Settings = Depends(settings_dep),
) -> MemberOut:
    """Desktop only: create an account with a password on this computer.

    On a website an administrator would be choosing the password of someone
    else's account, which may belong to other projects too; there, people
    join through an invite link and sign in as themselves.
    """
    if settings.deployment != "desktop":
        raise NotFound()
    if auth_service.email_is_taken(db, payload.email):
        raise Conflict("An account already exists for that email address")
    _check_person(db, ctx, payload.person_id)
    try:
        user = auth_service.create_user(
            db, email=payload.email, full_name=payload.full_name, password=payload.password
        )
    except WeakPassword as exc:
        raise UnprocessableConfig(str(exc)) from exc
    member = ProjectMember(
        project_id=ctx.project_id, user_id=user.id, role=payload.role, person_id=payload.person_id
    )
    db.add(member)
    db.flush()
    _audit(db, ctx, "member", member.id, "create")
    return _member_out(member)


@router.put("/project/members/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    payload: MemberUpdate,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
) -> MemberOut:
    member = _load_member(db, ctx, member_id)
    if payload.role is not None and payload.role is not member.role:
        # Checked before changing anything: demoting the final administrator
        # would leave nobody able to manage the project.
        try:
            auth_service.assert_not_last_admin(db, member)
        except auth_service.LastAdminError as exc:
            raise Conflict(str(exc)) from exc
        member.role = payload.role
    if payload.unlink_person:
        member.person_id = None
    elif payload.person_id is not None:
        _check_person(db, ctx, payload.person_id)
        member.person_id = payload.person_id
    _audit(db, ctx, "member", member_id, "update")
    return _member_out(member)


@router.delete("/project/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: int,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
) -> None:
    """Take someone out of the project. Their account, and other projects, stay."""
    member = _load_member(db, ctx, member_id)
    try:
        auth_service.assert_not_last_admin(db, member)
    except auth_service.LastAdminError as exc:
        raise Conflict(str(exc)) from exc
    db.delete(member)
    _audit(db, ctx, "member", member_id, "remove")


@router.post("/project/members/{member_id}/password", response_model=MemberOut)
def set_member_password(
    member_id: int,
    payload: PasswordSet,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
    settings: Settings = Depends(settings_dep),
) -> MemberOut:
    """Desktop only, for the same reason as adding a local account."""
    if settings.deployment != "desktop":
        raise NotFound()
    member = _load_member(db, ctx, member_id)
    try:
        auth_service.set_password(db, member.user, payload.password)
    except WeakPassword as exc:
        raise UnprocessableConfig(str(exc)) from exc
    # Setting a password also clears a lockout, which is how an administrator
    # restores access to someone locked out by failed attempts.
    member.user.failed_login_count = 0
    member.user.locked_until = None
    _audit(db, ctx, "member", member_id, "set-password")
    return _member_out(member)


# ------------------------------------------------------------------- invites


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _invite_out(invite: ProjectInvite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        role=invite.role,
        person_id=invite.person_id,
        single_use=invite.single_use,
        uses=invite.uses,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
    )


def _usable(invite: ProjectInvite) -> bool:
    return (
        invite.revoked_at is None
        and invite.expires_at > utcnow()
        and not (invite.single_use and invite.uses > 0)
    )


@router.get("/project/invites", response_model=list[InviteOut])
def list_invites(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(require_project_admin)
) -> list[InviteOut]:
    invites = db.scalars(
        select(ProjectInvite)
        .where(ProjectInvite.project_id == ctx.project_id)
        .order_by(ProjectInvite.created_at.desc())
    ).all()
    return [_invite_out(i) for i in invites if _usable(i)]


@router.post("/project/invites", response_model=InviteCreatedOut, status_code=201)
def create_invite(
    payload: InviteIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
) -> InviteCreatedOut:
    _check_person(db, ctx, payload.person_id)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    invite = ProjectInvite(
        project_id=ctx.project_id,
        token_hash=_hash(token),
        role=payload.role,
        person_id=payload.person_id,
        # A link that grants rights, or stands for one particular person,
        # works once. A plain staff link can go to a whole team.
        single_use=payload.role is not ProjectRole.STAFF or payload.person_id is not None,
        uses=0,
        created_by=ctx.user.id,
        expires_at=utcnow() + timedelta(days=payload.expires_in_days),
    )
    db.add(invite)
    db.flush()
    _audit(db, ctx, "invite", invite.id, "create")
    return InviteCreatedOut(**_invite_out(invite).model_dump(), token=token)


@router.delete("/project/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: int,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
) -> None:
    invite = db.get(ProjectInvite, invite_id)
    if invite is None or invite.project_id != ctx.project_id:
        raise NotFound("Invite not found")
    invite.revoked_at = utcnow()
    _audit(db, ctx, "invite", invite_id, "revoke")


def _find_invite(db: DbSession, token: str) -> ProjectInvite:
    invite = db.scalar(select(ProjectInvite).where(ProjectInvite.token_hash == _hash(token)))
    # Expired, used and unknown links all look the same from outside.
    if invite is None or not _usable(invite):
        raise NotFound("This invite link is not valid any more")
    return invite


@router.get("/invites/{token}", response_model=InvitePreviewOut)
def preview_invite(token: str, db: DbSession = Depends(get_db)) -> InvitePreviewOut:
    """What the link is for, shown before signing in to accept it."""
    invite = _find_invite(db, token)
    project = db.get(Project, invite.project_id)
    assert project is not None
    return InvitePreviewOut(project_name=project.name, role=invite.role)


@router.post("/invites/{token}/accept", response_model=ProjectOut)
def accept_invite(
    token: str, db: DbSession = Depends(get_db), user: User = Depends(current_user)
) -> ProjectOut:
    invite = _find_invite(db, token)
    # Counted with a conditional update, so two people opening a single-use
    # link at the same moment cannot both get in.
    claimed = db.execute(
        update(ProjectInvite)
        .where(
            ProjectInvite.id == invite.id,
            or_(ProjectInvite.single_use.is_(False), ProjectInvite.uses == 0),
        )
        .values(uses=ProjectInvite.uses + 1)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        raise NotFound("This invite link is not valid any more")
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == invite.project_id, ProjectMember.user_id == user.id
        )
    )
    if member is None:
        member = ProjectMember(
            project_id=invite.project_id,
            user_id=user.id,
            role=invite.role,
            person_id=invite.person_id,
        )
        db.add(member)
    else:
        # Already a member: a link never lowers anyone's role.
        if not at_least(member.role, invite.role):
            member.role = invite.role
        if member.person_id is None and invite.person_id is not None:
            member.person_id = invite.person_id
    db.add(
        orm.AuditLog(
            project_id=invite.project_id,
            user_id=user.id,
            entity_type="invite",
            entity_id=str(invite.id),
            action="accept",
        )
    )
    db.flush()
    db.refresh(member)
    return _project_out(member)
