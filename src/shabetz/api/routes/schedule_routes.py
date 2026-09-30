"""Schedule generation, retrieval and export."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth.rbac import can_view_all_assignments
from ...db import models as orm
from ...exporters.base import ExporterUnavailable, ExportFormat
from ...exporters.renderers import render
from ...repositories.db_repo import DbSchedulingRepository
from ...services.orchestration import JobOrchestrationService
from ...services.schedule_edit import Conflict, EditError, ScheduleEditor, SlotKey
from ..deps import ProjectContext, get_db, project_member, require_editor
from ..errors import ApiError, FeatureUnavailable, NotFound, UnprocessableConfig
from ..schemas import (
    AssignmentAddIn,
    AssignmentCheckIn,
    AssignmentCheckOut,
    AssignmentLockIn,
    AssignmentOut,
    AssignmentReassignIn,
    ConflictOut,
    GenerateRequest,
    ScheduleRunOut,
    ScheduleRunSummaryOut,
    SuggestionOut,
    SummaryOut,
    WarningOut,
)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


def _run_out(run: orm.ScheduleRun) -> ScheduleRunOut:
    payload = JobOrchestrationService.load_payload(run)
    return ScheduleRunOut(
        schedule_id=run.id,
        created_at=run.created_at,
        params=run.params_json,
        summary=SummaryOut.model_validate(run.summary_json),
        assignments=[AssignmentOut.model_validate(a) for a in payload["assignments"]],
        warnings=[WarningOut.model_validate(w) for w in payload["warnings"]],
    )


def _load_run(db: DbSession, schedule_id: str, ctx: ProjectContext) -> orm.ScheduleRun:
    run = db.get(orm.ScheduleRun, schedule_id)
    if run is None or run.project_id != ctx.project_id:
        raise NotFound("Schedule run not found")
    return run


@router.post("/generate", response_model=ScheduleRunOut, status_code=status.HTTP_201_CREATED)
def generate(
    payload: GenerateRequest,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    if payload.end_date < payload.start_date:
        raise UnprocessableConfig("End date must not precede start date")

    service = JobOrchestrationService(db, ctx.project_id)
    schedule_id, result, params = service.generate(
        payload.start_date, payload.end_date, keep_locked=payload.keep_locked
    )
    run = service.persist(schedule_id, result, params, created_by=ctx.user.id)
    db.flush()
    return _run_out(run)


@router.get("/runs", response_model=list[ScheduleRunSummaryOut])
def list_runs(
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[ScheduleRunSummaryOut]:
    rows = db.scalars(
        select(orm.ScheduleRun)
        .where(orm.ScheduleRun.project_id == ctx.project_id)
        .order_by(orm.ScheduleRun.created_at.desc())
        .limit(limit)
    ).all()
    return [
        ScheduleRunSummaryOut(
            schedule_id=row.id,
            created_at=row.created_at,
            params=row.params_json,
            summary=SummaryOut.model_validate(row.summary_json),
        )
        for row in rows
    ]


@router.get("/runs/{schedule_id}", response_model=ScheduleRunOut)
def get_run(
    schedule_id: str,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    return _run_out(_load_run(db, schedule_id, ctx))


# ------------------------------------------------------------ manual editing
#
# The schedule the engine produces is a proposal. These let an administrator or
# collaborator change it afterwards. A change that breaks a rule (someone on
# leave, double-booked, too little rest, missing a skill) is reported first and
# only saved once the caller acknowledges it.

_EDIT_STATUS = {"NOT_FOUND": 404, "CONFLICT": 409, "INVALID_CONFIGURATION": 422}


def _editor(db: DbSession, schedule_id: str, ctx: ProjectContext) -> ScheduleEditor:
    return ScheduleEditor(db, ctx.project_id, _load_run(db, schedule_id, ctx))


def _edit_error(exc: EditError) -> ApiError:
    return ApiError(exc.code, str(exc), _EDIT_STATUS.get(exc.code, 400))


def _conflicts_out(conflicts: list[Conflict]) -> list[ConflictOut]:
    return [
        ConflictOut(
            kind=c.kind.value, person_id=c.person_id, person_name=c.person_name, message=c.message
        )
        for c in conflicts
    ]


def _require_acknowledged(conflicts: list[Conflict], acknowledged: bool) -> None:
    if conflicts and not acknowledged:
        raise ApiError("SCHEDULE_CONFLICT", "; ".join(c.message for c in conflicts), 409)


def _audit_edit(
    db: DbSession, ctx: ProjectContext, schedule_id: str, action: str, detail: dict
) -> None:
    db.add(
        orm.AuditLog(
            user_id=ctx.user.id,
            project_id=ctx.project_id,
            entity_type="schedule_assignment",
            entity_id=schedule_id,
            action=action,
            after_json=detail,
        )
    )


@router.post("/runs/{schedule_id}/assignments/check", response_model=AssignmentCheckOut)
def check_assignment(
    schedule_id: str,
    payload: AssignmentCheckIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> AssignmentCheckOut:
    """What would go wrong if this person worked this shift. Changes nothing."""
    editor = _editor(db, schedule_id, ctx)
    key = SlotKey(payload.job_id, payload.template_id, payload.calendar_date)
    try:
        ignore = None
        requirement_id = None
        if payload.replaces_person_id is not None:
            ignore = editor.find(key, payload.replaces_person_id)
            requirement_id = ignore.satisfied_requirement_id
        conflicts = editor.conflicts_for(
            payload.person_id, key, ignore=ignore, requirement_id=requirement_id
        )
    except EditError as exc:
        raise _edit_error(exc) from exc
    return AssignmentCheckOut(conflicts=_conflicts_out(conflicts))


@router.get("/runs/{schedule_id}/suggestions", response_model=list[SuggestionOut])
def suggestions(
    schedule_id: str,
    job_id: int = Query(...),
    template_id: int = Query(...),
    calendar_date: date = Query(...),
    replaces_person_id: int | None = Query(default=None),
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> list[SuggestionOut]:
    """People who could cover this shift, fewest rule conflicts first."""
    editor = _editor(db, schedule_id, ctx)
    try:
        ranked = editor.suggest(
            SlotKey(job_id, template_id, calendar_date), replaces_person_id=replaces_person_id
        )
    except EditError as exc:
        raise _edit_error(exc) from exc
    return [
        SuggestionOut(
            person_id=person.id,
            person_name=person.full_name,
            division_id=person.division_id,
            shifts_in_schedule=load,
            conflicts=_conflicts_out(found),
        )
        for person, found, load in ranked
    ]


@router.put("/runs/{schedule_id}/assignments/lock", response_model=ScheduleRunOut)
def set_lock(
    schedule_id: str,
    payload: AssignmentLockIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    """Pin a shift so regenerating the schedule keeps it, or release it."""
    editor = _editor(db, schedule_id, ctx)
    try:
        editor.set_lock(
            SlotKey(payload.job_id, payload.template_id, payload.calendar_date),
            payload.person_id,
            payload.locked,
        )
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(
        db,
        ctx,
        schedule_id,
        "lock" if payload.locked else "unlock",
        payload.model_dump(mode="json"),
    )
    return _run_out(editor.run)


@router.put("/runs/{schedule_id}/assignments", response_model=ScheduleRunOut)
def reassign(
    schedule_id: str,
    payload: AssignmentReassignIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    editor = _editor(db, schedule_id, ctx)
    key = SlotKey(payload.job_id, payload.template_id, payload.calendar_date)
    try:
        conflicts = editor.reassign(key, payload.from_person_id, payload.to_person_id)
        _require_acknowledged(conflicts, payload.acknowledge_conflicts)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "reassign", payload.model_dump(mode="json"))
    return _run_out(editor.run)


@router.post(
    "/runs/{schedule_id}/assignments",
    response_model=ScheduleRunOut,
    status_code=status.HTTP_201_CREATED,
)
def add_assignment(
    schedule_id: str,
    payload: AssignmentAddIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    editor = _editor(db, schedule_id, ctx)
    key = SlotKey(payload.job_id, payload.template_id, payload.calendar_date)
    try:
        conflicts = editor.add(key, payload.person_id)
        _require_acknowledged(conflicts, payload.acknowledge_conflicts)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "add", payload.model_dump(mode="json"))
    return _run_out(editor.run)


@router.delete("/runs/{schedule_id}/assignments", response_model=ScheduleRunOut)
def remove_assignment(
    schedule_id: str,
    job_id: int = Query(...),
    template_id: int = Query(...),
    calendar_date: date = Query(...),
    person_id: int = Query(...),
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    editor = _editor(db, schedule_id, ctx)
    try:
        editor.remove(SlotKey(job_id, template_id, calendar_date), person_id)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(
        db,
        ctx,
        schedule_id,
        "remove",
        {
            "job_id": job_id,
            "template_id": template_id,
            "calendar_date": calendar_date.isoformat(),
            "person_id": person_id,
        },
    )
    return _run_out(editor.run)


@router.get("/runs/{schedule_id}/export")
def export_run(
    schedule_id: str,
    format: ExportFormat = Query(default=ExportFormat.CSV),
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(project_member),
) -> Response:
    run = _load_run(db, schedule_id, ctx)
    payload = JobOrchestrationService.load_payload(run)

    # Staff may export, but only their own shifts.
    if not can_view_all_assignments(ctx.role):
        person_id = ctx.member.person_id
        if person_id is None:
            payload = {"assignments": [], "warnings": []}
        else:
            payload = {
                "assignments": [a for a in payload["assignments"] if a["person_id"] == person_id],
                "warnings": [],
            }

    try:
        exported = render(format, payload, run.params_json, run.summary_json, schedule_id)
    except ExporterUnavailable as exc:
        raise FeatureUnavailable(str(exc)) from exc

    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"content-disposition": f'attachment; filename="{exported.filename}"'},
    )


@router.get("/me", response_model=list[AssignmentOut])
def my_assignments(
    schedule_id: str = Query(...),
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(project_member),
) -> list[AssignmentOut]:
    """A staff user's own shifts.

    Scoped by the member's linked person rather than by a supplied id, so
    changing an id in the URL cannot reveal someone else's schedule.
    """
    run = _load_run(db, schedule_id, ctx)
    payload = JobOrchestrationService.load_payload(run)
    person_id = ctx.member.person_id
    if person_id is None:
        return []
    return [
        AssignmentOut.model_validate(a)
        for a in payload["assignments"]
        if a["person_id"] == person_id
    ]


@router.get("/divisions")
def division_status(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> dict:
    repo = DbSchedulingRepository(db, ctx.project_id)
    divisions = repo.load_divisions()
    today = date.today()
    people = repo.load_people(today, today)
    counts: dict[int, int] = {}
    for person in people:
        counts[person.division_id] = counts.get(person.division_id, 0) + 1
    return {
        "divisions": [
            {
                "id": d.id,
                "name": d.name,
                "display_order": d.display_order,
                "headcount": counts.get(d.id, 0),
            }
            for d in divisions
        ]
    }
