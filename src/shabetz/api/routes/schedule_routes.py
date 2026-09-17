"""Schedule generation, retrieval and export."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...auth.rbac import can_view_all_assignments
from ...db import models as orm
from ...db.models import User
from ...exporters.base import ExporterUnavailable, ExportFormat
from ...exporters.renderers import render
from ...repositories.db_repo import DbSchedulingRepository
from ...services.orchestration import JobOrchestrationService
from ..deps import current_user, get_db, require_scheduler
from ..errors import FeatureUnavailable, NotFound, UnprocessableConfig
from ..schemas import (
    AssignmentOut,
    GenerateRequest,
    ScheduleRunOut,
    ScheduleRunSummaryOut,
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


def _load_run(db: DbSession, schedule_id: str) -> orm.ScheduleRun:
    run = db.get(orm.ScheduleRun, schedule_id)
    if run is None:
        raise NotFound("Schedule run not found")
    return run


@router.post("/generate", response_model=ScheduleRunOut, status_code=status.HTTP_201_CREATED)
def generate(
    payload: GenerateRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_scheduler),
) -> ScheduleRunOut:
    if payload.end_date < payload.start_date:
        raise UnprocessableConfig("End date must not precede start date")

    service = JobOrchestrationService(db)
    schedule_id, result, params = service.generate(payload.start_date, payload.end_date)
    run = service.persist(schedule_id, result, params, created_by=user.id)
    db.flush()
    return _run_out(run)


@router.get("/runs", response_model=list[ScheduleRunSummaryOut])
def list_runs(
    db: DbSession = Depends(get_db),
    _: User = Depends(require_scheduler),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[ScheduleRunSummaryOut]:
    rows = db.scalars(
        select(orm.ScheduleRun).order_by(orm.ScheduleRun.created_at.desc()).limit(limit)
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
    _: User = Depends(require_scheduler),
) -> ScheduleRunOut:
    return _run_out(_load_run(db, schedule_id))


@router.get("/runs/{schedule_id}/export")
def export_run(
    schedule_id: str,
    format: ExportFormat = Query(default=ExportFormat.CSV),
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    run = _load_run(db, schedule_id)
    payload = JobOrchestrationService.load_payload(run)

    # Staff may export, but only their own shifts.
    if not can_view_all_assignments(user.role):
        if user.person_id is None:
            payload = {"assignments": [], "warnings": []}
        else:
            payload = {
                "assignments": [
                    a for a in payload["assignments"] if a["person_id"] == user.person_id
                ],
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
    user: User = Depends(current_user),
) -> list[AssignmentOut]:
    """A staff user's own shifts.

    Scoped by the account's linked person rather than by a supplied id, so
    changing an id in the URL cannot reveal someone else's schedule.
    """
    run = _load_run(db, schedule_id)
    payload = JobOrchestrationService.load_payload(run)
    if user.person_id is None:
        return []
    return [
        AssignmentOut.model_validate(a)
        for a in payload["assignments"]
        if a["person_id"] == user.person_id
    ]


@router.get("/divisions")
def division_status(
    db: DbSession = Depends(get_db), _: User = Depends(current_user)
) -> dict:
    repo = DbSchedulingRepository(db)
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
