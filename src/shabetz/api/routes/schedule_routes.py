"""Schedule generation, retrieval and export."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth.rbac import can_view_all_assignments
from ...config import Settings
from ...db import models as orm
from ...db.base import utcnow
from ...exporters.base import ExporterUnavailable, ExportFormat
from ...exporters.renderers import render
from ...repositories.db_repo import DbSchedulingRepository
from ...services.notifications import send_email
from ...services.orchestration import JobOrchestrationService
from ...services.schedule_edit import Conflict, EditError, ScheduleEditor, SlotKey
from ..deps import ProjectContext, get_db, project_member, require_editor, settings_dep
from ..errors import ApiError, FeatureUnavailable, NotFound, UnprocessableConfig
from ..schemas import (
    AssignmentAddIn,
    AssignmentCheckIn,
    AssignmentCheckOut,
    AssignmentLockIn,
    AssignmentOut,
    AssignmentReassignIn,
    AssignmentSwapIn,
    ConflictOut,
    GenerateRequest,
    HistoryEntryOut,
    MyShiftsOut,
    PublishIn,
    PublishOut,
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
        published_at=run.published_at,
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
            published_at=row.published_at,
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

_AUDIT_ENTITY = "schedule_assignment"
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
    db: DbSession,
    ctx: ProjectContext,
    schedule_id: str,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """Record an edit with what it replaced and what it left, so it can be undone."""
    db.add(
        orm.AuditLog(
            user_id=ctx.user.id,
            project_id=ctx.project_id,
            entity_type=_AUDIT_ENTITY,
            entity_id=schedule_id,
            action=action,
            before_json=before,
            after_json=after,
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


@router.post("/runs/{schedule_id}/assignments/swap", response_model=ScheduleRunOut)
def swap_assignments(
    schedule_id: str,
    payload: AssignmentSwapIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    """Trade two people's shifts in one step, e.g. by dragging one onto the other."""
    editor = _editor(db, schedule_id, ctx)
    key_a = SlotKey(payload.a.job_id, payload.a.template_id, payload.a.calendar_date)
    key_b = SlotKey(payload.b.job_id, payload.b.template_id, payload.b.calendar_date)
    try:
        before = [
            editor.snapshot(key_a, payload.a_person_id),
            editor.snapshot(key_b, payload.b_person_id),
        ]
        conflicts = editor.swap(key_a, payload.a_person_id, key_b, payload.b_person_id)
        _require_acknowledged(conflicts, payload.acknowledge_conflicts)
        after = [
            editor.snapshot(key_a, payload.b_person_id),
            editor.snapshot(key_b, payload.a_person_id),
        ]
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "swap", {"items": before}, {"items": after})
    return _run_out(editor.run)


@router.put("/runs/{schedule_id}/assignments/lock", response_model=ScheduleRunOut)
def set_lock(
    schedule_id: str,
    payload: AssignmentLockIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    """Pin a shift so regenerating the schedule keeps it, or release it."""
    editor = _editor(db, schedule_id, ctx)
    key = SlotKey(payload.job_id, payload.template_id, payload.calendar_date)
    try:
        before = editor.snapshot(key, payload.person_id)
        editor.set_lock(key, payload.person_id, payload.locked)
        after = editor.snapshot(key, payload.person_id)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "lock" if payload.locked else "unlock", before, after)
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
        before = editor.snapshot(key, payload.from_person_id)
        conflicts = editor.reassign(key, payload.from_person_id, payload.to_person_id)
        _require_acknowledged(conflicts, payload.acknowledge_conflicts)
        after = editor.snapshot(key, payload.to_person_id)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "reassign", before, after)
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
        after = editor.snapshot(key, payload.person_id)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "add", None, after)
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
    key = SlotKey(job_id, template_id, calendar_date)
    try:
        before = editor.snapshot(key, person_id)
        editor.remove(key, person_id)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "remove", before, None)
    return _run_out(editor.run)


# ------------------------------------------------------------------ history

_EDIT_ACTIONS = {"reassign", "add", "remove", "lock", "unlock", "swap"}


def _first_item(blob: dict | None) -> dict:
    """The assignment an audit entry describes; a swap holds two, the first stands for both."""
    if not blob:
        return {}
    return (blob.get("items") or [blob])[0]


def _edit_log(db: DbSession, schedule_id: str, ctx: ProjectContext) -> list[orm.AuditLog]:
    """This schedule's edits, newest first."""
    return list(
        db.scalars(
            select(orm.AuditLog)
            .where(
                orm.AuditLog.project_id == ctx.project_id,
                orm.AuditLog.entity_type == _AUDIT_ENTITY,
                orm.AuditLog.entity_id == schedule_id,
            )
            .order_by(orm.AuditLog.id.desc())
        )
    )


def _undone_ids(entries: list[orm.AuditLog]) -> set[int]:
    """Edits already taken back. Each undo cancels the newest edit still standing."""
    undone: set[int] = set()
    pending = 0
    for entry in entries:  # newest first
        if entry.action == "undo":
            pending += 1
        elif pending:
            undone.add(entry.id)
            pending -= 1
    return undone


@router.get("/runs/{schedule_id}/history", response_model=list[HistoryEntryOut])
def history(
    schedule_id: str,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> list[HistoryEntryOut]:
    _load_run(db, schedule_id, ctx)
    entries = _edit_log(db, schedule_id, ctx)
    undone = _undone_ids(entries)
    user_ids = {e.user_id for e in entries if e.user_id}
    names = {
        u.id: u.full_name for u in db.scalars(select(orm.User).where(orm.User.id.in_(user_ids)))
    }
    out: list[HistoryEntryOut] = []
    top_found = False
    for entry in entries:
        if entry.action not in _EDIT_ACTIONS:
            continue
        is_undone = entry.id in undone
        can_undo = not is_undone and not top_found
        top_found = top_found or not is_undone
        shown = entry.after_json or entry.before_json or {}
        shown = _first_item(shown)
        out.append(
            HistoryEntryOut(
                id=entry.id,
                at=entry.at,
                user_name=names.get(entry.user_id or -1),
                action=entry.action,
                job_name=shown.get("job_name"),
                template_name=shown.get("template_name"),
                calendar_date=shown.get("calendar_date"),
                person_before=_first_item(entry.before_json).get("person_name"),
                person_after=_first_item(entry.after_json).get("person_name"),
                undone=is_undone,
                can_undo=can_undo,
            )
        )
    return out


@router.post("/runs/{schedule_id}/history/{entry_id}/undo", response_model=ScheduleRunOut)
def undo(
    schedule_id: str,
    entry_id: int,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> ScheduleRunOut:
    """Take back the newest edit still standing; older ones can then be undone in turn."""
    editor = _editor(db, schedule_id, ctx)
    entries = _edit_log(db, schedule_id, ctx)
    undone = _undone_ids(entries)
    target = next((e for e in entries if e.action in _EDIT_ACTIONS and e.id not in undone), None)
    if target is None or target.id != entry_id:
        raise ApiError("CONFLICT", "Only the most recent edit can be undone", 409)
    try:
        editor.restore(target.before_json, target.after_json)
        editor.save()
    except EditError as exc:
        raise _edit_error(exc) from exc
    _audit_edit(db, ctx, schedule_id, "undo", target.after_json, target.before_json)
    return _run_out(editor.run)


# ----------------------------------------------------------------- publishing


@router.post("/runs/{schedule_id}/publish", response_model=PublishOut)
def publish(
    schedule_id: str,
    payload: PublishIn,
    background: BackgroundTasks,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
    settings: Settings = Depends(settings_dep),
) -> PublishOut:
    """Make this schedule visible to staff, and optionally tell them by email."""
    run = _load_run(db, schedule_id, ctx)
    run.published_at = utcnow()
    run.published_by = ctx.user.id
    # Only one schedule is current for staff at a time.
    for other in db.scalars(
        select(orm.ScheduleRun).where(
            orm.ScheduleRun.project_id == ctx.project_id,
            orm.ScheduleRun.id != schedule_id,
            orm.ScheduleRun.published_at.is_not(None),
        )
    ):
        other.published_at = None
        other.published_by = None
    _audit_edit(db, ctx, schedule_id, "publish")
    db.flush()

    notified: int | None = None
    if payload.notify and settings.email_enabled:
        working = {a["person_id"] for a in JobOrchestrationService.load_payload(run)["assignments"]}
        recipients = sorted(
            {
                email
                for (email,) in db.execute(
                    select(orm.User.email)
                    .join(orm.ProjectMember, orm.ProjectMember.user_id == orm.User.id)
                    .where(
                        orm.ProjectMember.project_id == ctx.project_id,
                        orm.ProjectMember.person_id.in_(working),
                    )
                )
            }
        )
        notified = len(recipients)
        params = run.params_json
        background.add_task(
            send_email,
            settings,
            recipients,
            f"{ctx.project.name}: new schedule "
            f"{params.get('start_date')} – {params.get('end_date')}",
            f"A new schedule for {ctx.project.name} covering {params.get('start_date')} to "
            f"{params.get('end_date')} has been published.\n\nSign in to see your shifts.",
        )
    return PublishOut(
        published_at=run.published_at, notified=notified, email_configured=settings.email_enabled
    )


@router.post("/runs/{schedule_id}/unpublish", response_model=PublishOut)
def unpublish(
    schedule_id: str,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
    settings: Settings = Depends(settings_dep),
) -> PublishOut:
    run = _load_run(db, schedule_id, ctx)
    run.published_at = None
    run.published_by = None
    _audit_edit(db, ctx, schedule_id, "unpublish")
    return PublishOut(published_at=None, email_configured=settings.email_enabled)


@router.get("/my-shifts", response_model=MyShiftsOut)
def my_shifts(
    db: DbSession = Depends(get_db), ctx: ProjectContext = Depends(project_member)
) -> MyShiftsOut:
    """The person's own shifts from the published schedule; nothing until one is."""
    run = db.scalar(
        select(orm.ScheduleRun)
        .where(
            orm.ScheduleRun.project_id == ctx.project_id, orm.ScheduleRun.published_at.is_not(None)
        )
        .order_by(orm.ScheduleRun.published_at.desc())
        .limit(1)
    )
    if run is None:
        return MyShiftsOut()
    person_id = ctx.member.person_id
    mine = (
        []
        if person_id is None
        else [
            AssignmentOut.model_validate(a)
            for a in JobOrchestrationService.load_payload(run)["assignments"]
            if a["person_id"] == person_id
        ]
    )
    return MyShiftsOut(schedule_id=run.id, published_at=run.published_at, assignments=mine)


@router.get("/runs/{schedule_id}/export")
def export_run(
    schedule_id: str,
    format: ExportFormat = Query(default=ExportFormat.CSV),
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(project_member),
) -> Response:
    run = _load_run(db, schedule_id, ctx)
    if not can_view_all_assignments(ctx.role) and run.published_at is None:
        raise NotFound("Schedule run not found")
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
    if not can_view_all_assignments(ctx.role) and run.published_at is None:
        raise NotFound("Schedule run not found")
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
