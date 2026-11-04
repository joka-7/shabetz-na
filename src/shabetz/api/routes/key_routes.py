"""End-to-end encryption keys: each account stores and fetches its own.

The server only keeps what the browser uploads — a public key and two wrapped
copies of the secret key — and returns it to the same account so another
device can unwrap it with the passphrase or the recovery code. Nothing here
can read the secret key. See docs/E2EE-DESIGN.md §2 and §4.1.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ...db.base import utcnow
from ...db.models import MemberKey, User
from ..deps import current_user, get_db
from ..errors import Conflict, NotFound
from ..schemas import MemberKeyIn, MemberKeyOut, MemberKeyWraps

router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.get("/me", response_model=MemberKeyOut)
def my_key(
    user: User = Depends(current_user), db: DbSession = Depends(get_db, scope="function")
) -> MemberKey:
    key = db.get(MemberKey, user.id)
    if key is None:
        raise NotFound("No encryption key has been set up for this account")
    return key


@router.post("/me", response_model=MemberKeyOut, status_code=status.HTTP_201_CREATED)
def create_my_key(
    body: MemberKeyIn,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db, scope="function"),
) -> MemberKey:
    # A key pair is created once. Replacing it would orphan every project key
    # already sealed to the old public key, so that is a separate, deliberate
    # flow (losing both passphrase and recovery code, §4.7), not an overwrite.
    if db.get(MemberKey, user.id) is not None:
        raise Conflict("This account already has an encryption key")
    now = utcnow()
    key = MemberKey(user_id=user.id, created_at=now, updated_at=now, **body.model_dump())
    db.add(key)
    try:
        db.commit()
    except IntegrityError as exc:
        # Two first-time uploads raced; the other one won.
        db.rollback()
        raise Conflict("This account already has an encryption key") from exc
    return key


@router.put("/me/wraps", response_model=MemberKeyOut)
def rewrap_my_key(
    body: MemberKeyWraps,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db, scope="function"),
) -> MemberKey:
    """Store new wrapped copies of the same secret key: a changed passphrase or recovery code.

    The pair being replaced is kept in ``previous_wraps``, so a session used to
    overwrite them with junk cannot lock the member out for good.
    """
    key = db.get(MemberKey, user.id)
    if key is None:
        raise NotFound("No encryption key has been set up for this account")
    key.previous_wraps = {field: getattr(key, field) for field in MemberKeyWraps.model_fields}
    for field, value in body.model_dump().items():
        setattr(key, field, value)
    key.updated_at = utcnow()
    db.commit()
    return key
