"""Sign-in flows and account bootstrap."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..db.base import utcnow
from ..db.models import Project, ProjectMember, User
from ..domain.enums import ProjectRole
from .passwords import hash_password, needs_rehash, verify_password


class AuthError(Exception):
    """Sign-in failed.

    Deliberately carries no detail about which part failed: telling a caller
    that an address exists but the password was wrong is an account-enumeration
    oracle.
    """


class AccountLocked(AuthError):
    pass


def user_count(db: DbSession) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def setup_is_complete(db: DbSession) -> bool:
    """Whether the unauthenticated bootstrap route is still open.

    The window closes permanently the moment the first account exists.
    """
    return user_count(db) > 0


def create_user(
    db: DbSession,
    *,
    email: str,
    full_name: str,
    password: str | None = None,
    firebase_uid: str | None = None,
) -> User:
    user = User(
        email=email.strip().lower(),
        full_name=full_name.strip()[:120] or email.strip().lower(),
        password_hash=hash_password(password) if password else None,
        firebase_uid=firebase_uid,
    )
    db.add(user)
    db.flush()
    return user


DEFAULT_PROJECT_NAME = "My organization"


def create_project(db: DbSession, owner: User, name: str) -> Project:
    """A new project, administered by the account that created it."""
    project = Project(name=name.strip()[:120] or DEFAULT_PROJECT_NAME, created_by=owner.id)
    project.members = [ProjectMember(user_id=owner.id, role=ProjectRole.ADMIN)]
    db.add(project)
    db.flush()
    return project


def bootstrap_first_admin(
    db: DbSession, *, email: str, full_name: str, password: str, project_name: str = ""
) -> User:
    """The first account, and the project it administers."""
    if setup_is_complete(db):
        raise AuthError("Setup has already been completed")
    user = create_user(db, email=email, full_name=full_name, password=password)
    create_project(db, user, project_name)
    return user


def _find_by_email(db: DbSession, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


class LastAdminError(Exception):
    """Refused because it would leave a project with nobody to manage it.

    Distinct from AuthError: this is not a failed sign-in, it is a change that
    would lock everyone out of the project's membership for good.
    """


def project_admin_count(db: DbSession, project_id: int, *, excluding: int | None = None) -> int:
    query = (
        select(func.count())
        .select_from(ProjectMember)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == ProjectRole.ADMIN,
            User.is_active.is_(True),
        )
    )
    if excluding is not None:
        query = query.where(ProjectMember.id != excluding)
    return db.scalar(query) or 0


def assert_not_last_admin(db: DbSession, member: ProjectMember) -> None:
    """Guard a change that would strip a project's final administrator.

    Nobody else could then invite members, change roles or delete the
    project, and there is no way back short of editing the database.
    """
    if (
        member.role is ProjectRole.ADMIN
        and project_admin_count(db, member.project_id, excluding=member.id) == 0
    ):
        raise LastAdminError(
            "This is the project's only administrator; make someone else one first"
        )


def find_active_user_by_email(db: DbSession, email: str) -> User | None:
    user = _find_by_email(db, email)
    return user if user is not None and user.is_active else None


def email_is_taken(db: DbSession, email: str, *, excluding: int | None = None) -> bool:
    existing = _find_by_email(db, email)
    return existing is not None and existing.id != excluding


def set_password(db: DbSession, user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    # A password change should end sessions opened with the old one.
    from .sessions import revoke_all_for_user

    revoke_all_for_user(db, user.id)


def authenticate_password(
    db: DbSession, email: str, password: str, *, max_attempts: int, lockout_minutes: int
) -> User:
    user = _find_by_email(db, email)
    if user is None or not user.is_active:
        raise AuthError("Invalid email or password")

    if user.locked_until is not None and user.locked_until > utcnow():
        raise AccountLocked("Account is temporarily locked")

    if not verify_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= max_attempts:
            user.locked_until = utcnow() + timedelta(minutes=lockout_minutes)
            user.failed_login_count = 0
        # Commit the counter before raising. A failed sign-in aborts the
        # request transaction, which would otherwise roll this increment back
        # and leave the lockout permanently unreachable.
        db.commit()
        raise AuthError("Invalid email or password")

    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    return user


def authenticate_firebase(
    db: DbSession, *, uid: str, email: str, email_verified: bool, full_name: str
) -> User:
    """Sign in with a Google account verified by Firebase, signing up if new.

    Anyone may create an account this way; what they can reach is decided by
    project membership, which starts empty. An existing account is matched by
    its Firebase id, or else by address -- but only a verified address, since
    an unverified one proves nothing about who owns it.
    """
    if not email_verified:
        raise AuthError("This Google account has no verified email address")

    user = db.scalar(select(User).where(User.firebase_uid == uid))
    if user is None:
        user = _find_by_email(db, email)
        if user is None:
            user = create_user(db, email=email, full_name=full_name or email, firebase_uid=uid)
        elif user.firebase_uid is None:
            user.firebase_uid = uid
        else:
            # The address belongs to a different Google identity already.
            raise AuthError("This email address is linked to another sign-in")

    if not user.is_active:
        raise AuthError("This account has been disabled")

    user.last_login_at = utcnow()
    return user
