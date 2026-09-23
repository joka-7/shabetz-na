"""Account management.

The bootstrap route creates exactly one administrator and then closes forever,
so this is the only way any further account comes into existence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth import service as auth_service
from ...auth.passwords import WeakPassword
from ...auth.sessions import revoke_all_for_user
from ...db import models as orm
from ...db.base import utcnow
from ...db.models import User
from ..deps import get_db, require_admin
from ..errors import Conflict, NotFound, UnprocessableConfig
from ..schemas import PasswordSet, UserAdminOut, UserCreate, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


def _out(user: User) -> UserAdminOut:
    return UserAdminOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        person_id=user.person_id,
        has_password=bool(user.password_hash),
        has_google=bool(user.google_sub),
        last_login_at=user.last_login_at,
        is_locked=bool(user.locked_until and user.locked_until > utcnow()),
    )


def _audit(db: DbSession, actor: User, target_id: object, action: str) -> None:
    db.add(
        orm.AuditLog(user_id=actor.id, entity_type="user", entity_id=str(target_id), action=action)
    )


def _load(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("Account not found")
    return user


@router.get("", response_model=list[UserAdminOut])
def list_users(
    db: DbSession = Depends(get_db), _: User = Depends(require_admin)
) -> list[UserAdminOut]:
    rows = db.scalars(select(User).order_by(User.email)).all()
    return [_out(row) for row in rows]


@router.post("", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: DbSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserAdminOut:
    if auth_service.email_is_taken(db, payload.email):
        raise Conflict("An account already exists for that email address")

    if payload.person_id is not None and db.get(orm.Person, payload.person_id) is None:
        raise UnprocessableConfig(f"Person {payload.person_id} does not exist")

    try:
        user = auth_service.create_user(
            db,
            email=payload.email,
            full_name=payload.full_name,
            role=payload.role,
            password=payload.password,
            person_id=payload.person_id,
        )
    except WeakPassword as exc:
        raise UnprocessableConfig(str(exc)) from exc

    _audit(db, actor, user.id, "create")
    return _out(user)


@router.put("/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: DbSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserAdminOut:
    user = _load(db, user_id)

    # Check before mutating: demoting or deactivating the final administrator
    # would leave nobody able to manage the system, and the bootstrap route
    # closed permanently when the first account was created.
    removes_admin = (payload.role is not None and payload.role is not user.role) or (
        payload.is_active is False
    )
    if removes_admin:
        try:
            auth_service.assert_not_last_admin(db, user)
        except auth_service.LastAdminError as exc:
            raise Conflict(str(exc)) from exc

    if payload.person_id is not None and db.get(orm.Person, payload.person_id) is None:
        raise UnprocessableConfig(f"Person {payload.person_id} does not exist")

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.person_id is not None:
        user.person_id = payload.person_id
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    # A revoked or downgraded account must lose its open sessions at once;
    # otherwise the old rights would survive until they happened to expire.
    if payload.is_active is False or payload.role is not None:
        revoke_all_for_user(db, user.id)

    _audit(db, actor, user_id, "update")
    return _out(user)


@router.post("/{user_id}/password", response_model=UserAdminOut)
def set_user_password(
    user_id: int,
    payload: PasswordSet,
    db: DbSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserAdminOut:
    user = _load(db, user_id)
    try:
        auth_service.set_password(db, user, payload.password)
    except WeakPassword as exc:
        raise UnprocessableConfig(str(exc)) from exc

    # Setting a password also clears a lockout, which is how an administrator
    # restores access to someone locked out by failed attempts.
    user.failed_login_count = 0
    user.locked_until = None

    _audit(db, actor, user_id, "set-password")
    return _out(user)


@router.post("/{user_id}/revoke-sessions", response_model=UserAdminOut)
def revoke_sessions(
    user_id: int,
    db: DbSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserAdminOut:
    user = _load(db, user_id)
    revoke_all_for_user(db, user.id)
    _audit(db, actor, user_id, "revoke-sessions")
    return _out(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: DbSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> None:
    user = _load(db, user_id)
    try:
        auth_service.assert_not_last_admin(db, user)
    except auth_service.LastAdminError as exc:
        raise Conflict(str(exc)) from exc

    # Deactivated rather than deleted: the audit log and any schedule runs the
    # account created still refer to it.
    user.is_active = False
    revoke_all_for_user(db, user.id)
    _audit(db, actor, user_id, "deactivate")
