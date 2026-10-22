"""What is waiting on the signed-in member, and what has happened in the project."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ...auth.rbac import can_edit_configuration, can_review_time_off
from ...db import models as orm
from ...domain.enums import SwapStatus, TimeOffStatus
from ..deps import ProjectContext, get_db, project_member, require_project_admin

router = APIRouter(prefix="/api", tags=["inbox"])


class InboxOut(BaseModel):
    """Counts for the badges on the tabs: things only this member can move along."""

    swaps: int = 0
    time_off: int = 0


@router.get("/inbox", response_model=InboxOut)
def inbox(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> InboxOut:
    def count(query) -> int:  # type: ignore[no-untyped-def]
        return db.scalar(select(func.count()).select_from(query.subquery())) or 0

    swaps = 0
    me = ctx.member.person_id
    if me is not None:
        # Offered to me, and only I can answer.
        swaps += count(
            select(orm.SwapRequest.id).where(
                orm.SwapRequest.project_id == ctx.project_id,
                orm.SwapRequest.to_person_id == me,
                orm.SwapRequest.status == SwapStatus.AWAITING_COLLEAGUE,
            )
        )
    if can_edit_configuration(ctx.role):
        swaps += count(
            select(orm.SwapRequest.id).where(
                orm.SwapRequest.project_id == ctx.project_id,
                orm.SwapRequest.status == SwapStatus.AWAITING_MANAGER,
            )
        )
    time_off = 0
    if can_review_time_off(ctx.role):
        time_off = count(
            select(orm.TimeOff.id).where(
                orm.TimeOff.project_id == ctx.project_id,
                orm.TimeOff.status == TimeOffStatus.PENDING,
            )
        )
    return InboxOut(swaps=swaps, time_off=time_off)


class ActivityOut(BaseModel):
    id: int
    at: datetime
    user_name: str | None
    entity_type: str
    entity_id: str | None
    action: str


@router.get("/project/activity", response_model=list[ActivityOut])
def activity(
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_project_admin),
    limit: int = Query(default=100, ge=1, le=500),
    before: int | None = Query(default=None, description="Page back from this entry id."),
) -> list[ActivityOut]:
    """Who changed what, newest first. What each change contained stays out of it."""
    query = (
        select(orm.AuditLog, orm.User.full_name)
        .outerjoin(orm.User, orm.User.id == orm.AuditLog.user_id)
        .where(orm.AuditLog.project_id == ctx.project_id)
        .order_by(orm.AuditLog.id.desc())
        .limit(limit)
    )
    if before is not None:
        query = query.where(orm.AuditLog.id < before)
    return [
        ActivityOut(
            id=entry.id,
            at=entry.at,
            user_name=name,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            action=entry.action,
        )
        for entry, name in db.execute(query)
    ]
