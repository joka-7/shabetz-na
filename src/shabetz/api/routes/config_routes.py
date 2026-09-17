"""Configuration CRUD.

Everything the original specification hardcoded is edited through here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from ...db import models as orm
from ...db.models import User
from ...services.orchestration import JobOrchestrationService
from ...services.settings_service import SchedulingSettings, load_settings, save_settings
from ..deps import current_user, get_db, require_admin
from ..errors import Conflict, NotFound, UnprocessableConfig
from ..schemas import (
    DivisionIn,
    DivisionOut,
    FeasibilityOut,
    JobIn,
    JobOut,
    PersonIn,
    PersonOut,
    PersonSkillIn,
    ProficiencyLevelIn,
    ProficiencyLevelOut,
    RequirementOut,
    SettingsIn,
    SettingsOut,
    ShiftTemplateIn,
    ShiftTemplateOut,
    SkillIn,
    SkillOut,
    SplitDayRequest,
)

router = APIRouter(prefix="/api/config", tags=["configuration"])


def _audit(db: DbSession, user: User, entity: str, entity_id: object, action: str) -> None:
    db.add(
        orm.AuditLog(user_id=user.id, entity_type=entity, entity_id=str(entity_id), action=action)
    )


# ----------------------------------------------------------------- divisions


@router.get("/divisions", response_model=list[DivisionOut])
def list_divisions(
    db: DbSession = Depends(get_db), _: User = Depends(current_user)
) -> list[orm.Division]:
    return list(
        db.scalars(
            select(orm.Division)
            .where(orm.Division.is_active.is_(True))
            .order_by(orm.Division.display_order, orm.Division.id)
        )
    )


@router.post("/divisions", response_model=DivisionOut, status_code=status.HTTP_201_CREATED)
def create_division(
    payload: DivisionIn, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> orm.Division:
    row = orm.Division(**payload.model_dump())
    db.add(row)
    db.flush()
    _audit(db, user, "division", row.id, "create")
    return row


@router.put("/divisions/{division_id}", response_model=DivisionOut)
def update_division(
    division_id: int,
    payload: DivisionIn,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> orm.Division:
    row = db.get(orm.Division, division_id)
    if row is None or not row.is_active:
        raise NotFound("Division not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    _audit(db, user, "division", division_id, "update")
    return row


@router.delete("/divisions/{division_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_division(
    division_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> None:
    row = db.get(orm.Division, division_id)
    if row is None:
        raise NotFound("Division not found")
    in_use = db.scalar(
        select(orm.Person).where(
            orm.Person.division_id == division_id, orm.Person.is_active.is_(True)
        )
    )
    if in_use is not None:
        raise Conflict("Division still has people assigned to it")
    # Soft delete: historical schedule runs reference this row and must stay
    # renderable.
    row.is_active = False
    _audit(db, user, "division", division_id, "delete")


# ---------------------------------------------------------- proficiency ladder


@router.get("/proficiency-levels", response_model=list[ProficiencyLevelOut])
def list_levels(
    db: DbSession = Depends(get_db), _: User = Depends(current_user)
) -> list[orm.ProficiencyLevel]:
    return list(
        db.scalars(
            select(orm.ProficiencyLevel)
            .where(orm.ProficiencyLevel.is_active.is_(True))
            .order_by(orm.ProficiencyLevel.rank)
        )
    )


@router.post(
    "/proficiency-levels", response_model=ProficiencyLevelOut, status_code=status.HTTP_201_CREATED
)
def create_level(
    payload: ProficiencyLevelIn,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> orm.ProficiencyLevel:
    clash = db.scalar(select(orm.ProficiencyLevel).where(orm.ProficiencyLevel.rank == payload.rank))
    if clash is not None:
        raise Conflict(f"Rank {payload.rank} is already used by {clash.name!r}")
    row = orm.ProficiencyLevel(**payload.model_dump())
    db.add(row)
    db.flush()
    _audit(db, user, "proficiency_level", row.id, "create")
    return row


@router.delete("/proficiency-levels/{level_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_level(
    level_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> None:
    row = db.get(orm.ProficiencyLevel, level_id)
    if row is None:
        raise NotFound("Level not found")
    referenced = db.scalar(
        select(orm.PersonSkill).where(orm.PersonSkill.level_id == level_id)
    ) or db.scalar(
        select(orm.JobSkillRequirement).where(orm.JobSkillRequirement.min_level_id == level_id)
    )
    if referenced is not None:
        raise Conflict("Level is still referenced by a person's skill or a job requirement")
    row.is_active = False
    _audit(db, user, "proficiency_level", level_id, "delete")


# -------------------------------------------------------------------- skills


@router.get("/skills", response_model=list[SkillOut])
def list_skills(
    db: DbSession = Depends(get_db), _: User = Depends(current_user)
) -> list[orm.Skill]:
    return list(
        db.scalars(select(orm.Skill).where(orm.Skill.is_active.is_(True)).order_by(orm.Skill.name))
    )


@router.post("/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill(
    payload: SkillIn, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> orm.Skill:
    row = orm.Skill(**payload.model_dump())
    db.add(row)
    db.flush()
    _audit(db, user, "skill", row.id, "create")
    return row


# ----------------------------------------------------------- shift templates


@router.get("/shift-templates", response_model=list[ShiftTemplateOut])
def list_templates(
    db: DbSession = Depends(get_db), _: User = Depends(current_user)
) -> list[orm.ShiftTemplate]:
    return list(
        db.scalars(
            select(orm.ShiftTemplate)
            .where(orm.ShiftTemplate.is_active.is_(True))
            .order_by(orm.ShiftTemplate.start_hour)
        )
    )


@router.post(
    "/shift-templates", response_model=ShiftTemplateOut, status_code=status.HTTP_201_CREATED
)
def create_template(
    payload: ShiftTemplateIn,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> orm.ShiftTemplate:
    row = orm.ShiftTemplate(**payload.model_dump())
    db.add(row)
    db.flush()
    _audit(db, user, "shift_template", row.id, "create")
    return row


@router.post(
    "/shift-templates/split-day",
    response_model=list[ShiftTemplateOut],
    status_code=status.HTTP_201_CREATED,
)
def split_day(
    payload: SplitDayRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[orm.ShiftTemplate]:
    """Generate evenly divided windows.

    Hand-entering equal blocks is the common case and is tedious; this does not
    restrict the model, which still accepts arbitrary windows.
    """
    duration = payload.total_hours / payload.shifts
    created: list[orm.ShiftTemplate] = []
    for index in range(payload.shifts):
        row = orm.ShiftTemplate(
            name=f"{payload.name_prefix} {index + 1}",
            start_hour=(payload.start_hour + index * duration) % 24,
            duration_hours=duration,
        )
        db.add(row)
        created.append(row)
    db.flush()
    for row in created:
        _audit(db, user, "shift_template", row.id, "create")
    return created


@router.delete("/shift-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> None:
    row = db.get(orm.ShiftTemplate, template_id)
    if row is None:
        raise NotFound("Shift template not found")
    row.is_active = False
    db.execute(
        delete(orm.JobShiftTemplate).where(orm.JobShiftTemplate.shift_template_id == template_id)
    )
    _audit(db, user, "shift_template", template_id, "delete")


# ---------------------------------------------------------------------- jobs


def _job_out(row: orm.Job) -> JobOut:
    return JobOut(
        id=row.id,
        name=row.name,
        required_people_per_shift=row.required_people_per_shift,
        division_policy=row.division_policy,
        priority=row.priority,
        is_active=row.is_active,
        shift_template_ids=[link.shift_template_id for link in row.shift_links],
        requirements=[
            RequirementOut(
                id=req.id,
                skill_id=req.skill_id,
                min_level_id=req.min_level_id,
                required_count=req.required_count,
                is_leadership=req.is_leadership,
                skill_name=req.skill.name if req.skill else None,
            )
            for req in row.requirements
        ],
    )


def _load_job(db: DbSession, job_id: int) -> orm.Job:
    row = db.scalar(
        select(orm.Job)
        .where(orm.Job.id == job_id)
        .options(
            selectinload(orm.Job.shift_links),
            selectinload(orm.Job.requirements).selectinload(orm.JobSkillRequirement.skill),
        )
    )
    if row is None or not row.is_active:
        raise NotFound("Job not found")
    return row


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(db: DbSession = Depends(get_db), _: User = Depends(current_user)) -> list[JobOut]:
    rows = db.scalars(
        select(orm.Job)
        .where(orm.Job.is_active.is_(True))
        .options(
            selectinload(orm.Job.shift_links),
            selectinload(orm.Job.requirements).selectinload(orm.JobSkillRequirement.skill),
        )
        .order_by(orm.Job.id)
    ).all()
    return [_job_out(row) for row in rows]


def _apply_job(db: DbSession, row: orm.Job, payload: JobIn) -> None:
    row.name = payload.name
    row.required_people_per_shift = payload.required_people_per_shift
    row.division_policy = payload.division_policy
    row.priority = payload.priority

    for template_id in payload.shift_template_ids:
        if db.get(orm.ShiftTemplate, template_id) is None:
            raise UnprocessableConfig(f"Shift template {template_id} does not exist")
    for req in payload.requirements:
        if db.get(orm.Skill, req.skill_id) is None:
            raise UnprocessableConfig(f"Skill {req.skill_id} does not exist")
        if db.get(orm.ProficiencyLevel, req.min_level_id) is None:
            raise UnprocessableConfig(f"Proficiency level {req.min_level_id} does not exist")

    row.shift_links = [
        orm.JobShiftTemplate(shift_template_id=tid) for tid in payload.shift_template_ids
    ]
    row.requirements = [orm.JobSkillRequirement(**req.model_dump()) for req in payload.requirements]


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobIn, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> JobOut:
    row = orm.Job(name=payload.name, required_people_per_shift=payload.required_people_per_shift)
    db.add(row)
    _apply_job(db, row, payload)
    db.flush()
    _audit(db, user, "job", row.id, "create")
    return _job_out(_load_job(db, row.id))


@router.put("/jobs/{job_id}", response_model=JobOut)
def update_job(
    job_id: int,
    payload: JobIn,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> JobOut:
    row = _load_job(db, job_id)
    _apply_job(db, row, payload)
    db.flush()
    _audit(db, user, "job", job_id, "update")
    return _job_out(_load_job(db, job_id))


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> None:
    row = _load_job(db, job_id)
    row.is_active = False
    _audit(db, user, "job", job_id, "delete")


# -------------------------------------------------------------------- people


def _person_out(row: orm.Person) -> PersonOut:
    return PersonOut(
        id=row.id,
        full_name=row.full_name,
        division_id=row.division_id,
        external_ref=row.external_ref,
        is_active=row.is_active,
        working_weekdays=sorted(d.weekday for d in row.working_days),
        skills=[PersonSkillIn(skill_id=s.skill_id, level_id=s.level_id) for s in row.skills],
    )


def _people_query():  # type: ignore[no-untyped-def]
    return (
        select(orm.Person)
        .where(orm.Person.is_active.is_(True))
        .options(selectinload(orm.Person.skills), selectinload(orm.Person.working_days))
        .order_by(orm.Person.full_name)
    )


@router.get("/people", response_model=list[PersonOut])
def list_people(
    db: DbSession = Depends(get_db), _: User = Depends(current_user)
) -> list[PersonOut]:
    return [_person_out(row) for row in db.scalars(_people_query()).all()]


def _apply_person(db: DbSession, row: orm.Person, payload: PersonIn) -> None:
    if db.get(orm.Division, payload.division_id) is None:
        raise UnprocessableConfig(f"Division {payload.division_id} does not exist")
    row.full_name = payload.full_name
    row.division_id = payload.division_id
    row.external_ref = payload.external_ref
    row.working_days = [
        orm.PersonWorkingDay(weekday=d) for d in sorted(set(payload.working_weekdays))
    ]
    row.skills = [orm.PersonSkill(skill_id=s.skill_id, level_id=s.level_id) for s in payload.skills]


@router.post("/people", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonIn, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> PersonOut:
    row = orm.Person(full_name=payload.full_name, division_id=payload.division_id)
    db.add(row)
    _apply_person(db, row, payload)
    db.flush()
    _audit(db, user, "person", row.id, "create")
    return _person_out(row)


@router.put("/people/{person_id}", response_model=PersonOut)
def update_person(
    person_id: int,
    payload: PersonIn,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> PersonOut:
    row = db.get(orm.Person, person_id)
    if row is None or not row.is_active:
        raise NotFound("Person not found")
    _apply_person(db, row, payload)
    db.flush()
    _audit(db, user, "person", person_id, "update")
    return _person_out(row)


@router.delete("/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> None:
    row = db.get(orm.Person, person_id)
    if row is None:
        raise NotFound("Person not found")
    row.is_active = False
    _audit(db, user, "person", person_id, "delete")


# ------------------------------------------------------------------ settings


@router.get("/settings", response_model=SettingsOut)
def get_settings_route(
    db: DbSession = Depends(get_db), _: User = Depends(current_user)
) -> SettingsOut:
    return SettingsOut(**load_settings(db).model_dump())


@router.put("/settings", response_model=SettingsOut)
def put_settings(
    payload: SettingsIn, db: DbSession = Depends(get_db), user: User = Depends(require_admin)
) -> SettingsOut:
    current = load_settings(db)
    updated = SchedulingSettings(**payload.model_dump(), setup_completed=current.setup_completed)
    save_settings(db, updated)
    _audit(db, user, "settings", "scheduling", "update")
    return SettingsOut(**updated.model_dump())


@router.get("/feasibility", response_model=FeasibilityOut)
def feasibility(db: DbSession = Depends(get_db), _: User = Depends(current_user)) -> FeasibilityOut:
    report = JobOrchestrationService(db).feasibility()
    return FeasibilityOut.model_validate(report)
