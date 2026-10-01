"""Shift swaps: a member hands a published shift to a colleague, a manager signs off."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth.rbac import can_edit_configuration
from ...db import models as orm
from ...db.base import utcnow
from ...domain.enums import SwapStatus
from ...services.orchestration import JobOrchestrationService
from ...services.schedule_edit import EditError, ScheduleEditor, SlotKey
from ..deps import ProjectContext, get_db, project_member, require_editor
from ..errors import ApiError, Conflict, Forbidden, NotFound, UnprocessableConfig
from ..schemas import ColleagueOut, ConflictOut, SwapDecision, SwapIn, SwapOut
from .schedule_routes import _audit_edit, _conflicts_out, _require_acknowledged

router = APIRouter(prefix="/api/swaps", tags=["swaps"])

OPEN = (SwapStatus.AWAITING_COLLEAGUE, SwapStatus.AWAITING_MANAGER)


def _own_person(ctx: ProjectContext) -> int:
    person_id = ctx.member.person_id
    if person_id is None:
        raise UnprocessableConfig("This account is not linked to a person record")
    return person_id


def _published_run(db: DbSession, ctx: ProjectContext) -> orm.ScheduleRun:
    run = db.scalar(
        select(orm.ScheduleRun)
        .where(
            orm.ScheduleRun.project_id == ctx.project_id, orm.ScheduleRun.published_at.is_not(None)
        )
        .order_by(orm.ScheduleRun.published_at.desc())
        .limit(1)
    )
    if run is None:
        raise UnprocessableConfig("No schedule has been published yet")
    return run


def _load(db: DbSession, swap_id: int, ctx: ProjectContext) -> orm.SwapRequest:
    row = db.get(orm.SwapRequest, swap_id)
    if row is None or row.project_id != ctx.project_id:
        raise NotFound("Swap request not found")
    return row


def _names(db: DbSession, ids: set[int]) -> dict[int, str]:
    return {p.id: p.full_name for p in db.scalars(select(orm.Person).where(orm.Person.id.in_(ids)))}


def _out(row: orm.SwapRequest, names: dict[int, str], ctx: ProjectContext) -> SwapOut:
    me = ctx.member.person_id
    editor = can_edit_configuration(ctx.role)
    return SwapOut(
        id=row.id,
        status=row.status.value,
        schedule_id=row.schedule_id,
        job_id=row.job_id,
        template_id=row.template_id,
        calendar_date=row.calendar_date,
        job_name=row.job_name,
        template_name=row.template_name,
        from_person_id=row.from_person_id,
        from_name=names.get(row.from_person_id, "?"),
        to_person_id=row.to_person_id,
        to_name=names.get(row.to_person_id, "?"),
        note=row.note,
        review_note=row.review_note,
        created_at=row.created_at,
        can_accept=row.status is SwapStatus.AWAITING_COLLEAGUE and me == row.to_person_id,
        can_cancel=row.status in OPEN and row.requested_by == ctx.user.id,
        can_decide=row.status is SwapStatus.AWAITING_MANAGER and editor,
    )


def _render(db: DbSession, rows: list[orm.SwapRequest], ctx: ProjectContext) -> list[SwapOut]:
    ids = {r.from_person_id for r in rows} | {r.to_person_id for r in rows}
    names = _names(db, ids)
    return [_out(r, names, ctx) for r in rows]


@router.get("/colleagues", response_model=list[ColleagueOut])
def colleagues(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> list[ColleagueOut]:
    """People a shift can be handed to: those who have an account to answer with."""
    rows = db.execute(
        select(orm.Person.id, orm.Person.full_name)
        .join(orm.ProjectMember, orm.ProjectMember.person_id == orm.Person.id)
        .where(
            orm.ProjectMember.project_id == ctx.project_id,
            orm.Person.is_active.is_(True),
            orm.Person.id != (ctx.member.person_id or -1),
        )
        .order_by(orm.Person.full_name)
    ).all()
    return [ColleagueOut(person_id=pid, name=name) for pid, name in rows]


@router.get("", response_model=list[SwapOut])
def list_swaps(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> list[SwapOut]:
    query = select(orm.SwapRequest).where(orm.SwapRequest.project_id == ctx.project_id)
    if not can_edit_configuration(ctx.role):
        me = ctx.member.person_id or -1
        query = query.where(
            (orm.SwapRequest.from_person_id == me) | (orm.SwapRequest.to_person_id == me)
        )
    rows = list(db.scalars(query.order_by(orm.SwapRequest.id.desc()).limit(100)))
    return _render(db, rows, ctx)


@router.post("", response_model=SwapOut, status_code=status.HTTP_201_CREATED)
def request_swap(
    payload: SwapIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(project_member),
) -> SwapOut:
    me = _own_person(ctx)
    run = _published_run(db, ctx)
    mine = next(
        (
            a
            for a in JobOrchestrationService.load_payload(run)["assignments"]
            if a["person_id"] == me
            and a["job_id"] == payload.job_id
            and a["template_id"] == payload.template_id
            and a["calendar_date"] == payload.calendar_date.isoformat()
        ),
        None,
    )
    if mine is None:
        raise NotFound("That shift is not one of yours")
    if payload.to_person_id == me:
        raise UnprocessableConfig("Choose a colleague")
    colleague = db.scalar(
        select(orm.ProjectMember).where(
            orm.ProjectMember.project_id == ctx.project_id,
            orm.ProjectMember.person_id == payload.to_person_id,
        )
    )
    if colleague is None:
        raise UnprocessableConfig("That colleague has no account to answer with")
    already = db.scalar(
        select(orm.SwapRequest).where(
            orm.SwapRequest.project_id == ctx.project_id,
            orm.SwapRequest.schedule_id == run.id,
            orm.SwapRequest.job_id == payload.job_id,
            orm.SwapRequest.template_id == payload.template_id,
            orm.SwapRequest.calendar_date == payload.calendar_date,
            orm.SwapRequest.from_person_id == me,
            orm.SwapRequest.status.in_(OPEN),
        )
    )
    if already is not None:
        raise Conflict("This shift already has an open swap request")

    row = orm.SwapRequest(
        project_id=ctx.project_id,
        schedule_id=run.id,
        job_id=payload.job_id,
        template_id=payload.template_id,
        calendar_date=payload.calendar_date,
        job_name=mine["job_name"],
        template_name=mine["template_name"],
        from_person_id=me,
        to_person_id=payload.to_person_id,
        note=payload.note,
        requested_by=ctx.user.id,
    )
    db.add(row)
    db.flush()
    return _render(db, [row], ctx)[0]


def _answer(row: orm.SwapRequest, ctx: ProjectContext, accept: bool) -> None:
    if row.to_person_id != ctx.member.person_id:
        raise Forbidden("Only the colleague it was offered to can answer")
    if row.status is not SwapStatus.AWAITING_COLLEAGUE:
        raise Conflict("This request is no longer waiting for an answer")
    row.status = SwapStatus.AWAITING_MANAGER if accept else SwapStatus.DECLINED


@router.post("/{swap_id}/accept", response_model=SwapOut)
def accept(
    swap_id: int, db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> SwapOut:
    row = _load(db, swap_id, ctx)
    _answer(row, ctx, True)
    return _render(db, [row], ctx)[0]


@router.post("/{swap_id}/decline", response_model=SwapOut)
def decline(
    swap_id: int, db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> SwapOut:
    row = _load(db, swap_id, ctx)
    _answer(row, ctx, False)
    return _render(db, [row], ctx)[0]


@router.post("/{swap_id}/cancel", response_model=SwapOut)
def cancel(
    swap_id: int, db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> SwapOut:
    row = _load(db, swap_id, ctx)
    if row.requested_by != ctx.user.id:
        raise Forbidden("Only the person who asked can cancel it")
    if row.status not in OPEN:
        raise Conflict("This request is already settled")
    row.status = SwapStatus.CANCELLED
    return _render(db, [row], ctx)[0]


def _editor_for(db: DbSession, row: orm.SwapRequest, ctx: ProjectContext) -> ScheduleEditor:
    run = db.get(orm.ScheduleRun, row.schedule_id)
    if run is None or run.project_id != ctx.project_id:
        raise Conflict("The schedule this was asked against no longer exists")
    return ScheduleEditor(db, ctx.project_id, run)


@router.get("/{swap_id}/conflicts", response_model=list[ConflictOut])
def swap_conflicts(
    swap_id: int,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> list[ConflictOut]:
    """Rules the swap would break if approved, so a manager can decide knowingly."""
    row = _load(db, swap_id, ctx)
    editor = _editor_for(db, row, ctx)
    key = SlotKey(row.job_id, row.template_id, row.calendar_date)
    try:
        current = editor.find(key, row.from_person_id)
        found = editor.conflicts_for(
            row.to_person_id,
            key,
            ignore=current,
            requirement_id=current.satisfied_requirement_id,
        )
    except EditError as exc:
        raise Conflict("The schedule has changed since this was asked") from exc
    return _conflicts_out(found)


@router.post("/{swap_id}/approve", response_model=SwapOut)
def approve(
    swap_id: int,
    payload: SwapDecision,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> SwapOut:
    row = _load(db, swap_id, ctx)
    if row.status is not SwapStatus.AWAITING_MANAGER:
        raise Conflict("This request is not waiting for a decision")
    editor = _editor_for(db, row, ctx)
    key = SlotKey(row.job_id, row.template_id, row.calendar_date)
    try:
        before = editor.snapshot(key, row.from_person_id)
        conflicts = editor.reassign(key, row.from_person_id, row.to_person_id)
        _require_acknowledged(conflicts, payload.acknowledge_conflicts)
        after = editor.snapshot(key, row.to_person_id)
        editor.save()
    except EditError as exc:
        raise ApiError(
            "CONFLICT", f"The schedule has changed since this was asked: {exc}", 409
        ) from exc
    _audit_edit(db, ctx, row.schedule_id, "reassign", before, after)
    row.status = SwapStatus.APPROVED
    row.reviewed_by = ctx.user.id
    row.reviewed_at = utcnow()
    row.review_note = payload.note
    return _render(db, [row], ctx)[0]


@router.post("/{swap_id}/deny", response_model=SwapOut)
def deny(
    swap_id: int,
    payload: SwapDecision,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> SwapOut:
    row = _load(db, swap_id, ctx)
    if row.status not in OPEN:
        raise Conflict("This request is already settled")
    row.status = SwapStatus.DENIED
    row.reviewed_by = ctx.user.id
    row.reviewed_at = utcnow()
    row.review_note = payload.note
    return _render(db, [row], ctx)[0]
