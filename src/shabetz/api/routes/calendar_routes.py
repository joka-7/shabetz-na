"""Calendar feeds: each member's published shifts, at an address calendar apps can fetch."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth.throttle import FailureThrottle
from ...config import Settings
from ...db import models as orm
from ...db.base import utcnow
from ...services.calendar_feed import render_ics
from ...services.orchestration import JobOrchestrationService
from ...services.settings_service import load_settings
from ..deps import (
    ProjectContext,
    client_address,
    get_db,
    link_throttle,
    project_member,
    settings_dep,
)
from ..errors import NotFound, TooManyRequests

router = APIRouter(prefix="/api", tags=["calendar"])

TOKEN_BYTES = 32


class CalendarLinkOut(BaseModel):
    enabled: bool
    # Only in the answer that creates it: the server keeps just its hash.
    path: str | None = None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.get("/me/calendar", response_model=CalendarLinkOut)
def calendar_status(ctx: ProjectContext = Depends(project_member)) -> CalendarLinkOut:
    return CalendarLinkOut(enabled=ctx.member.calendar_token_hash is not None)


@router.post("/me/calendar", response_model=CalendarLinkOut)
def create_calendar_link(
    db: DbSession = Depends(get_db, scope="function"), ctx: ProjectContext = Depends(project_member)
) -> CalendarLinkOut:
    """A new feed address for this member in this project; any older one stops working."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    ctx.member.calendar_token_hash = _hash(token)
    db.flush()
    return CalendarLinkOut(enabled=True, path=f"/api/calendar/{token}.ics")


@router.delete("/me/calendar", status_code=status.HTTP_204_NO_CONTENT)
def remove_calendar_link(
    db: DbSession = Depends(get_db, scope="function"), ctx: ProjectContext = Depends(project_member)
) -> None:
    ctx.member.calendar_token_hash = None


@router.get("/calendar/{token}.ics", include_in_schema=False)
def calendar_feed(
    token: str,
    request: Request,
    db: DbSession = Depends(get_db, scope="function"),
    settings: Settings = Depends(settings_dep),
    throttle: FailureThrottle = Depends(link_throttle),
) -> Response:
    """The member's shifts in the published schedule; an empty calendar until there is one."""
    address = client_address(request, settings)
    if throttle.is_blocked(address):
        raise TooManyRequests(throttle.retry_after_seconds(address))
    member = db.scalar(
        select(orm.ProjectMember).where(orm.ProjectMember.calendar_token_hash == _hash(token))
    )
    # A feed is as good as a sign-in, so it ends with the account's access.
    if (
        member is None
        or not member.user.is_active
        or not settings.email_is_allowed(member.user.email)
    ):
        throttle.record_failure(address)
        raise NotFound("Calendar not found")

    project = db.get(orm.Project, member.project_id)
    assert project is not None
    run = db.scalar(
        select(orm.ScheduleRun)
        .where(
            orm.ScheduleRun.project_id == member.project_id,
            orm.ScheduleRun.published_at.is_not(None),
        )
        .order_by(orm.ScheduleRun.published_at.desc())
        .limit(1)
    )
    shifts: list[dict] = []
    start = utcnow().date()
    if run is not None and member.person_id is not None:
        start = date.fromisoformat(run.params_json["start_date"])
        shifts = [
            a
            for a in JobOrchestrationService.load_payload(run)["assignments"]
            if a["person_id"] == member.person_id
        ]
    body = render_ics(
        calendar_name=project.name,
        schedule_start=start,
        time_zone=load_settings(db, member.project_id).timezone,
        assignments=shifts,
        generated_at=utcnow(),
    )
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        # Private to the person whose address it is; never kept by a shared cache.
        headers={"cache-control": "private, max-age=900"},
    )
