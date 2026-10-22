"""Time-off requests and their review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth.rbac import can_review_time_off, can_view_all_assignments
from ...db import models as orm
from ...db.base import utcnow
from ...domain.enums import TimeOffStatus
from ...services.orchestration import JobOrchestrationService
from ..deps import ProjectContext, get_db, project_member, require_editor
from ..errors import Forbidden, NotFound, UnprocessableConfig
from ..schemas import PublishedShiftOut, TimeOffIn, TimeOffOut, TimeOffReview

router = APIRouter(prefix="/api/time-off", tags=["time off"])


def _with_published_shifts(db: DbSession, ctx: ProjectContext, row: orm.TimeOff) -> TimeOffOut:
    """The request, with any published shifts it now clashes with.

    Approving an absence does not change a schedule already published; the
    person stays on those shifts until someone moves them. Saying which shifts
    those are is what keeps the gap from going unnoticed.
    """
    out = TimeOffOut.model_validate(row)
    run = db.scalar(
        select(orm.ScheduleRun)
        .where(
            orm.ScheduleRun.project_id == ctx.project_id,
            orm.ScheduleRun.published_at.is_not(None),
        )
        .order_by(orm.ScheduleRun.published_at.desc())
        .limit(1)
    )
    if run is None:
        return out
    start, end = row.start_date.isoformat(), row.end_date.isoformat()
    clashes = [
        PublishedShiftOut(
            calendar_date=a["calendar_date"],
            job_name=a["job_name"],
            template_name=a["template_name"],
        )
        for a in JobOrchestrationService.load_payload(run)["assignments"]
        if a["person_id"] == row.person_id and start <= a["calendar_date"] <= end
    ]
    return out.model_copy(update={"published_shifts": clashes})


@router.post("", response_model=TimeOffOut, status_code=status.HTTP_201_CREATED)
def submit(
    payload: TimeOffIn,
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(project_member),
) -> TimeOffOut:
    if payload.end_date < payload.start_date:
        raise UnprocessableConfig("End date must not precede start date")
    if (payload.start_hour is None) != (payload.end_hour is None):
        raise UnprocessableConfig("Give both a start and an end time, or neither")
    if payload.start_hour is not None and payload.end_hour <= payload.start_hour:  # type: ignore[operator]
        raise UnprocessableConfig("End time must be after start time")

    own_person = ctx.member.person_id
    reviewer = can_review_time_off(ctx.role)
    if reviewer:
        person_id = payload.person_id or own_person
    else:
        # Staff may only ever request for themselves; a supplied person_id that
        # is not their own is refused rather than quietly ignored.
        if payload.person_id is not None and payload.person_id != own_person:
            raise Forbidden("You may only request time off for yourself")
        person_id = own_person

    if person_id is None:
        raise UnprocessableConfig("This account is not linked to a person record")
    person = db.get(orm.Person, person_id)
    if person is None or person.project_id != ctx.project_id:
        raise NotFound("Person not found")

    user = ctx.user
    row = orm.TimeOff(
        project_id=ctx.project_id,
        person_id=person_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        start_hour=payload.start_hour,
        end_hour=payload.end_hour,
        reason=payload.reason,
        # A reviewer recording an absence directly is already the decision;
        # a staff request must wait for one.
        status=TimeOffStatus.APPROVED if reviewer else TimeOffStatus.PENDING,
        requested_by=user.id,
        reviewed_by=user.id if reviewer else None,
        reviewed_at=utcnow() if reviewer else None,
    )
    db.add(row)
    db.flush()
    if reviewer:
        return _with_published_shifts(db, ctx, row)
    return TimeOffOut.model_validate(row)


@router.get("", response_model=list[TimeOffOut])
def list_requests(
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(project_member),
    status_filter: TimeOffStatus | None = Query(default=None, alias="status"),
    person_id: int | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[orm.TimeOff]:
    query = (
        select(orm.TimeOff)
        .where(orm.TimeOff.project_id == ctx.project_id)
        .order_by(orm.TimeOff.start_date.desc())
    )

    if can_view_all_assignments(ctx.role):
        if person_id is not None:
            query = query.where(orm.TimeOff.person_id == person_id)
    else:
        # Scoped in the query itself, so a staff member cannot read another
        # person's requests by supplying their id.
        if ctx.member.person_id is None:
            return []
        query = query.where(orm.TimeOff.person_id == ctx.member.person_id)

    if status_filter is not None:
        query = query.where(orm.TimeOff.status == status_filter)

    return list(db.scalars(query.limit(limit)))


def _load(db: DbSession, request_id: int, ctx: ProjectContext) -> orm.TimeOff:
    row = db.get(orm.TimeOff, request_id)
    if row is None or row.project_id != ctx.project_id:
        raise NotFound("Time-off request not found")
    return row


def _review(
    db: DbSession, request_id: int, ctx: ProjectContext, outcome: TimeOffStatus, note: str | None
) -> orm.TimeOff:
    row = _load(db, request_id, ctx)
    if row.status is not TimeOffStatus.PENDING:
        raise UnprocessableConfig(f"Request is already {row.status.value.lower()}")
    row.status = outcome
    row.reviewed_by = ctx.user.id
    row.reviewed_at = utcnow()
    row.review_note = note
    return row


@router.post("/{request_id}/approve", response_model=TimeOffOut)
def approve(
    request_id: int,
    payload: TimeOffReview | None = None,
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(require_editor),
) -> TimeOffOut:
    row = _review(db, request_id, ctx, TimeOffStatus.APPROVED, payload.note if payload else None)
    return _with_published_shifts(db, ctx, row)


@router.post("/{request_id}/deny", response_model=TimeOffOut)
def deny(
    request_id: int,
    payload: TimeOffReview | None = None,
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(require_editor),
) -> orm.TimeOff:
    return _review(db, request_id, ctx, TimeOffStatus.DENIED, payload.note if payload else None)


@router.post("/{request_id}/cancel", response_model=TimeOffOut)
def cancel(
    request_id: int,
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(project_member),
) -> orm.TimeOff:
    row = _load(db, request_id, ctx)
    if not can_review_time_off(ctx.role) and row.person_id != ctx.member.person_id:
        raise Forbidden("You may only cancel your own requests")
    if row.status not in (TimeOffStatus.PENDING, TimeOffStatus.APPROVED):
        raise UnprocessableConfig(f"Request is already {row.status.value.lower()}")
    row.status = TimeOffStatus.CANCELLED
    return row
