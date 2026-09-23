"""Sign-in flows and account bootstrap."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..db.base import utcnow
from ..db.models import User
from ..domain.enums import UserRole
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
    role: UserRole,
    password: str | None = None,
    person_id: int | None = None,
) -> User:
    user = User(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        role=role,
        password_hash=hash_password(password) if password else None,
        person_id=person_id,
    )
    db.add(user)
    db.flush()
    return user


def bootstrap_first_admin(db: DbSession, *, email: str, full_name: str, password: str) -> User:
    if setup_is_complete(db):
        raise AuthError("Setup has already been completed")
    return create_user(db, email=email, full_name=full_name, role=UserRole.ADMIN, password=password)


def _find_by_email(db: DbSession, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


class LastAdminError(Exception):
    """Refused because it would leave the system with no way in.

    Distinct from AuthError: this is not a failed sign-in, it is a
    configuration change that would lock everyone out permanently.
    """


def active_admin_count(db: DbSession, *, excluding: int | None = None) -> int:
    query = (
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    )
    if excluding is not None:
        query = query.where(User.id != excluding)
    return db.scalar(query) or 0


def assert_not_last_admin(db: DbSession, user: User) -> None:
    """Guard a change that would strip the final administrator.

    Demoting or deactivating the only admin leaves nobody able to manage
    configuration or restore access, and the bootstrap route is long closed by
    then, so the database would have to be edited by hand.
    """
    if (
        user.role is UserRole.ADMIN
        and user.is_active
        and active_admin_count(db, excluding=user.id) == 0
    ):
        raise LastAdminError("This is the only administrator; promote another account first")


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


def authenticate_google(db: DbSession, *, google_sub: str, email: str) -> User:
    """Sign in an existing invited account via Google.

    Google is a sign-in path, never a sign-up path.  If an unrecognised address
    could create an account, anyone with a Google account could walk in.
    """
    user = db.scalar(select(User).where(User.google_sub == google_sub))
    if user is None:
        user = _find_by_email(db, email)
        if user is None:
            raise AuthError("No account exists for this Google identity")
        user.google_sub = google_sub

    if not user.is_active:
        raise AuthError("No account exists for this Google identity")

    user.last_login_at = utcnow()
    return user
