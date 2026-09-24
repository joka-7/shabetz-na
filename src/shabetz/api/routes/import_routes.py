"""Adding configuration in bulk: pasted lists and imported spreadsheets.

Typing a roster one person at a time is where a first setup stalls, and the
roster almost always already exists in a spreadsheet. These routes accept it
as it is, and the people import previews before it writes anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...db import models as orm
from ...imports.catalog import ensure_divisions, ensure_levels, ensure_skills, name_key
from ...imports.people import (
    Column,
    ImportPlan,
    ImportRequestError,
    apply_people_import,
    plan_people_import,
)
from ...imports.tables import MAX_UPLOAD_BYTES, TableError, read_table
from ..deps import ProjectContext, get_db, require_editor
from ..errors import ApiError, UnprocessableConfig
from ..schemas import (
    BulkNamesIn,
    BulkResultOut,
    BulkTemplatesIn,
    ImportProblemOut,
    ImportRowOut,
    PeopleImportIn,
    PeopleImportOut,
    TableOut,
)
from .config_routes import _audit

router = APIRouter(prefix="/api/config", tags=["configuration"])


@router.post("/divisions/bulk", response_model=BulkResultOut)
def bulk_divisions(
    payload: BulkNamesIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> BulkResultOut:
    """Add divisions to the end of the rotation, in the order given."""
    result = ensure_divisions(db, ctx.project_id, payload.names)
    for name in result.created:
        _audit(db, ctx, "division", result.rows[name_key(name)].id, "create")
    return BulkResultOut(created=result.created, existing=result.existing)


@router.post("/skills/bulk", response_model=BulkResultOut)
def bulk_skills(
    payload: BulkNamesIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> BulkResultOut:
    result = ensure_skills(db, ctx.project_id, payload.names)
    for name in result.created:
        _audit(db, ctx, "skill", result.rows[name_key(name)].id, "create")
    return BulkResultOut(created=result.created, existing=result.existing)


@router.post("/proficiency-levels/bulk", response_model=BulkResultOut)
def bulk_levels(
    payload: BulkNamesIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> BulkResultOut:
    """Add rungs above the current top of the ladder, weakest first."""
    result = ensure_levels(db, ctx.project_id, payload.names)
    for name in result.created:
        _audit(db, ctx, "proficiency_level", result.rows[name_key(name)].id, "create")
    return BulkResultOut(created=result.created, existing=result.existing)


@router.post("/shift-templates/bulk", response_model=BulkResultOut)
def bulk_templates(
    payload: BulkTemplatesIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> BulkResultOut:
    """Add shift windows, skipping any whose name is already in use."""
    taken = {
        name_key(row.name)
        for row in db.scalars(
            select(orm.ShiftTemplate).where(
                orm.ShiftTemplate.project_id == ctx.project_id,
                orm.ShiftTemplate.is_active.is_(True),
            )
        )
    }
    created: list[orm.ShiftTemplate] = []
    existing: list[str] = []
    for template in payload.templates:
        name = " ".join(template.name.split())
        if not name:
            continue
        if name_key(name) in taken:
            existing.append(name)
            continue
        taken.add(name_key(name))
        row = orm.ShiftTemplate(
            project_id=ctx.project_id, **{**template.model_dump(), "name": name}
        )
        db.add(row)
        created.append(row)
    db.flush()
    for row in created:
        _audit(db, ctx, "shift_template", row.id, "create")
    return BulkResultOut(created=[row.name for row in created], existing=existing)


@router.post("/import/table", response_model=TableOut)
async def read_uploaded_table(
    file: UploadFile = File(...), _: ProjectContext = Depends(require_editor)
) -> TableOut:
    """Read an uploaded .xlsx or .csv into rows of text, without saving anything."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError("FILE_TOO_LARGE", "The file is larger than 5 MB", 413)
    try:
        rows = read_table(data, file.filename or "")
    except TableError as exc:
        raise ApiError(exc.code.upper(), str(exc), 422) from exc
    return TableOut(rows=rows)


def _plan_out(plan: ImportPlan) -> PeopleImportOut:
    return PeopleImportOut(
        applied=plan.applied,
        to_create=plan.to_create,
        new_divisions=plan.new_divisions,
        new_skills=plan.new_skills,
        rows=[
            ImportRowOut(
                line=row.line,
                full_name=row.full_name,
                division=row.division,
                status=row.status,
                working_weekdays=row.working_weekdays,
                skills=row.skills,
                problems=[ImportProblemOut(code=p.code, value=p.value) for p in row.problems],
            )
            for row in plan.rows
        ],
    )


@router.post("/import/people", response_model=PeopleImportOut)
def import_people(
    payload: PeopleImportIn,
    db: DbSession = Depends(get_db),
    ctx: ProjectContext = Depends(require_editor),
) -> PeopleImportOut:
    """Preview a roster import, or with ``apply`` perform it.

    Divisions and skills the file names but that do not exist yet are created
    along with the people who need them.
    """
    try:
        plan = plan_people_import(
            db,
            ctx.project_id,
            [Column(role=c.role, skill_name=c.skill_name) for c in payload.columns],
            payload.rows,
            payload.default_division_id,
            payload.default_weekdays,
        )
    except ImportRequestError as exc:
        raise UnprocessableConfig(str(exc)) from exc
    if payload.apply:
        for person in apply_people_import(db, ctx.project_id, plan):
            _audit(db, ctx, "person", person.id, "import")
    return _plan_out(plan)
