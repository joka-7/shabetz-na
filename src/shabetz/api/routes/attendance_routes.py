"""Who is actually there today.

Anyone who can see the whole schedule can read attendance; only editors mark it.
Approved time off is reported alongside, so a person already known to be away
is not marked present by mistake.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth.rbac import can_review_time_off
from ...db import models as orm
from ...db.base import utcnow
from ...domain.enums import TimeOffStatus
from ..deps import ProjectContext, get_db, require_editor, require_viewer
from ..errors import NotFound
from ..schemas import AttendanceBulkIn, AttendanceMarkIn, AttendanceRowOut

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

NOTE_MAX = 500


def _clean(note: str | None) -> str | None:
    text = (note or "").strip()[:NOTE_MAX]
    return text or None


def _rows(db: DbSession, ctx: ProjectContext, day: date) -> list[AttendanceRowOut]:
    people = db.scalars(
        select(orm.Person)
        .where(orm.Person.project_id == ctx.project_id, orm.Person.is_active.is_(True))
        .order_by(orm.Person.full_name)
    ).all()
    marks = {
        row.person_id: row
        for row in db.scalars(
            select(orm.Attendance).where(
                orm.Attendance.project_id == ctx.project_id, orm.Attendance.calendar_date == day
            )
        )
    }
    leave = {
        row.person_id: row
        for row in db.scalars(
            select(orm.TimeOff).where(
                orm.TimeOff.project_id == ctx.project_id,
                orm.TimeOff.status == TimeOffStatus.APPROVED,
                orm.TimeOff.start_date <= day,
                orm.TimeOff.end_date >= day,
            )
        )
    }
    # Why someone is away is theirs to share with those who review it.
    show_reason = can_review_time_off(ctx.role)
    out: list[AttendanceRowOut] = []
    for person in people:
        mark = marks.get(person.id)
        off = leave.get(person.id)
        out.append(
            AttendanceRowOut(
                person_id=person.id,
                full_name=person.full_name,
                division_id=person.division_id,
                status=mark.status if mark else None,
                note=mark.note if mark else None,
                on_leave=off is not None,
                leave_reason=off.reason if (off is not None and show_reason) else None,
            )
        )
    return out


def _person(db: DbSession, ctx: ProjectContext, person_id: int) -> orm.Person:
    person = db.get(orm.Person, person_id)
    if person is None or person.project_id != ctx.project_id or not person.is_active:
        raise NotFound("Person not found")
    return person


@router.get("", response_model=list[AttendanceRowOut])
def day_attendance(
    day: date = Query(alias="date"),
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(require_viewer),
) -> list[AttendanceRowOut]:
    return _rows(db, ctx, day)


@router.put("", response_model=list[AttendanceRowOut])
def mark(
    payload: AttendanceMarkIn,
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(require_editor),
) -> list[AttendanceRowOut]:
    """Mark one person; no status clears the mark. Returns the day, refreshed."""
    _person(db, ctx, payload.person_id)
    row = db.scalar(
        select(orm.Attendance).where(
            orm.Attendance.person_id == payload.person_id,
            orm.Attendance.calendar_date == payload.calendar_date,
        )
    )
    note = _clean(payload.note)
    if payload.status is None:
        # No status means "not marked": the mark and its reason go together.
        if row is not None:
            db.delete(row)
    else:
        if row is None:
            row = orm.Attendance(
                project_id=ctx.project_id,
                person_id=payload.person_id,
                calendar_date=payload.calendar_date,
                status=payload.status,
            )
            db.add(row)
        row.status = payload.status
        row.note = note
        row.marked_by = ctx.user.id
        row.marked_at = utcnow()
    db.flush()
    return _rows(db, ctx, payload.calendar_date)


@router.post("/bulk", response_model=list[AttendanceRowOut])
def mark_many(
    payload: AttendanceBulkIn,
    db: DbSession = Depends(get_db, scope="function"),
    ctx: ProjectContext = Depends(require_editor),
) -> list[AttendanceRowOut]:
    """Mark many at once, such as everyone present; people already marked are left alone."""
    current = {
        row.person_id: row
        for row in db.scalars(
            select(orm.Attendance).where(
                orm.Attendance.project_id == ctx.project_id,
                orm.Attendance.calendar_date == payload.calendar_date,
            )
        )
    }
    people = db.scalars(
        select(orm.Person).where(
            orm.Person.project_id == ctx.project_id, orm.Person.is_active.is_(True)
        )
    ).all()
    wanted = set(payload.person_ids) if payload.person_ids is not None else None
    for person in people:
        if wanted is not None and person.id not in wanted:
            continue
        if person.id in current:
            continue
        db.add(
            orm.Attendance(
                project_id=ctx.project_id,
                person_id=person.id,
                calendar_date=payload.calendar_date,
                status=payload.status,
                marked_by=ctx.user.id,
            )
        )
    db.flush()
    return _rows(db, ctx, payload.calendar_date)
