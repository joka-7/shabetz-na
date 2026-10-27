"""Saving a project to a file and bringing it back.

A backup holds the project's configuration, its people and their time off, with
everything referring to everything else by name rather than by database id, so
a file made on one server loads into any other project. Schedules, swap
requests, accounts and the audit trail are not included: schedules are rebuilt
from this data, and accounts belong to whoever signs in.

Importing is a merge by name: what the file names is created if missing and
brought in line with the file if it exists; nothing in the project is removed.
The preview and the import are the same code, the preview simply being undone,
so they can never disagree about what a file means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import models as orm
from ..domain.enums import DivisionPolicy, TimeOffStatus
from ..services.settings_service import SchedulingSettings, load_settings, save_settings
from .catalog import ensure_divisions, ensure_levels, ensure_skills, name_key

FORMAT = "shabetz-project"
VERSION = 1

Name = Annotated[str, Field(min_length=1, max_length=160)]


class _Division(BaseModel):
    name: Name
    color: str | None = Field(default=None, max_length=32)


class _Level(BaseModel):
    name: Name


class _Skill(BaseModel):
    name: Name
    description: str | None = None


class _Template(BaseModel):
    name: Name
    start_hour: float = Field(ge=0, lt=24)
    duration_hours: float = Field(gt=0, le=24)
    color: str | None = Field(default=None, max_length=32)


class _Requirement(BaseModel):
    skill: Name
    min_level: Name
    required_count: int | None = Field(default=None, ge=1)
    is_leadership: bool = False


class _Job(BaseModel):
    name: Name
    required_people_per_shift: int = Field(default=1, ge=1)
    division_policy: DivisionPolicy = DivisionPolicy.ACTIVE_DIVISION_PREFERRED
    priority: int | None = None
    notes: str | None = Field(default=None, max_length=2000)
    shift_templates: list[Name] = Field(default_factory=list, max_length=200)
    requirements: list[_Requirement] = Field(default_factory=list, max_length=200)


class _PersonSkill(BaseModel):
    skill: Name
    level: Name


class _Person(BaseModel):
    full_name: Name
    external_ref: str | None = Field(default=None, max_length=160)
    division: Name
    working_weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(default_factory=list)
    skills: list[_PersonSkill] = Field(default_factory=list, max_length=200)


class _TimeOff(BaseModel):
    person: Name
    start_date: date
    end_date: date
    start_hour: float | None = Field(default=None, ge=0, lt=24)
    end_hour: float | None = Field(default=None, gt=0, le=24)
    reason: str | None = None
    status: TimeOffStatus = TimeOffStatus.APPROVED


class _Settings(BaseModel):
    rest_period_hours: float = Field(default=8.0, ge=0, le=48)
    rotation_enabled: bool = True
    rotation_block_days: int = Field(default=2, ge=1, le=365)
    rotation_anchor_date: date | None = None
    timezone: str = Field(default="UTC", max_length=64)
    week_start: int = Field(default=0, ge=0, le=6)


class Backup(BaseModel):
    format: Literal["shabetz-project"]
    version: int = Field(ge=1, le=VERSION)
    exported_at: str | None = None
    project_name: str = ""
    settings: _Settings = Field(default_factory=_Settings)
    divisions: list[_Division] = Field(default_factory=list, max_length=500)
    levels: list[_Level] = Field(default_factory=list, max_length=100)
    skills: list[_Skill] = Field(default_factory=list, max_length=500)
    shift_templates: list[_Template] = Field(default_factory=list, max_length=500)
    jobs: list[_Job] = Field(default_factory=list, max_length=1000)
    people: list[_Person] = Field(default_factory=list, max_length=10000)
    time_off: list[_TimeOff] = Field(default_factory=list, max_length=50000)


# ------------------------------------------------------------------- export


def export_project(db: Session, project_id: int) -> dict:
    """Everything above, as plain data ready to be written as JSON."""
    project = db.get(orm.Project, project_id)
    settings = load_settings(db, project_id)

    def active(model):  # type: ignore[no-untyped-def]
        return select(model).where(model.project_id == project_id, model.is_active.is_(True))

    divisions = db.scalars(
        active(orm.Division).order_by(orm.Division.display_order, orm.Division.id)
    ).all()
    levels = db.scalars(active(orm.ProficiencyLevel).order_by(orm.ProficiencyLevel.rank)).all()
    skills = db.scalars(active(orm.Skill).order_by(orm.Skill.id)).all()
    templates = db.scalars(active(orm.ShiftTemplate).order_by(orm.ShiftTemplate.id)).all()
    jobs = db.scalars(
        active(orm.Job)
        .order_by(orm.Job.id)
        .options(
            selectinload(orm.Job.shift_links).selectinload(orm.JobShiftTemplate.shift_template),
            selectinload(orm.Job.requirements).selectinload(orm.JobSkillRequirement.skill),
            selectinload(orm.Job.requirements).selectinload(orm.JobSkillRequirement.min_level),
        )
    ).all()
    people = db.scalars(
        active(orm.Person).options(
            selectinload(orm.Person.skills).selectinload(orm.PersonSkill.skill),
            selectinload(orm.Person.skills).selectinload(orm.PersonSkill.level),
            selectinload(orm.Person.working_days),
            selectinload(orm.Person.division),
            selectinload(orm.Person.time_off),
        )
    ).all()
    # Names are stored encrypted, so the database cannot sort them.
    people = sorted(people, key=lambda p: (p.full_name.casefold(), p.id))

    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "project_name": project.name if project else "",
        "settings": settings.model_dump(
            mode="json", exclude={"organization_name", "setup_completed"}
        ),
        "divisions": [{"name": d.name, "color": d.color} for d in divisions],
        "levels": [{"name": level.name} for level in levels],
        "skills": [{"name": s.name, "description": s.description} for s in skills],
        "shift_templates": [
            {
                "name": t.name,
                "start_hour": t.start_hour,
                "duration_hours": t.duration_hours,
                "color": t.color,
            }
            for t in templates
        ],
        "jobs": [
            {
                "name": j.name,
                "required_people_per_shift": j.required_people_per_shift,
                "division_policy": j.division_policy.value,
                "priority": j.priority,
                "notes": j.notes,
                "shift_templates": [link.shift_template.name for link in j.shift_links],
                "requirements": [
                    {
                        "skill": r.skill.name,
                        "min_level": r.min_level.name,
                        "required_count": r.required_count,
                        "is_leadership": r.is_leadership,
                    }
                    for r in j.requirements
                ],
            }
            for j in jobs
        ],
        "people": [
            {
                "full_name": p.full_name,
                "external_ref": p.external_ref,
                "division": p.division.name,
                "working_weekdays": sorted(d.weekday for d in p.working_days),
                "skills": [{"skill": s.skill.name, "level": s.level.name} for s in p.skills],
            }
            for p in people
        ],
        "time_off": [
            {
                "person": p.full_name,
                "start_date": t.start_date.isoformat(),
                "end_date": t.end_date.isoformat(),
                "start_hour": t.start_hour,
                "end_hour": t.end_hour,
                "reason": t.reason,
                "status": t.status.value,
            }
            for p in people
            for t in p.time_off
        ],
    }


# ------------------------------------------------------------------- import


@dataclass
class Counts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass
class Problem:
    code: str
    value: str


@dataclass
class BackupPlan:
    counts: dict[str, Counts] = field(default_factory=dict)
    problems: list[Problem] = field(default_factory=list)
    applied: bool = False

    def count(self, entity: str) -> Counts:
        return self.counts.setdefault(entity, Counts())


def _set(row: object, **values: object) -> bool:
    """Assign what differs; whether anything did."""
    changed = False
    for attribute, value in values.items():
        if getattr(row, attribute) != value:
            setattr(row, attribute, value)
            changed = True
    return changed


def _tally(counts: Counts, *, created: bool, changed: bool) -> None:
    if created:
        counts.created += 1
    elif changed:
        counts.updated += 1
    else:
        counts.unchanged += 1


def _by_key(db: Session, model, project_id: int, attribute: str) -> dict:  # type: ignore[no-untyped-def]
    rows = db.scalars(select(model).where(model.project_id == project_id)).all()
    mapping: dict = {}
    # Visible rows win over removed ones of the same name.
    for row in sorted(rows, key=lambda r: bool(r.is_active)):
        mapping[name_key(getattr(row, attribute))] = row
    return mapping


def merge_backup(db: Session, project_id: int, backup: Backup) -> BackupPlan:
    """Bring the project in line with the backup. Writes; the caller decides
    whether to keep it."""
    plan = BackupPlan()

    # ---- settings
    current = load_settings(db, project_id)
    merged = SchedulingSettings(
        **backup.settings.model_dump(),
        organization_name=current.organization_name,
        setup_completed=current.setup_completed,
    )
    settings_counts = plan.count("settings")
    if merged == current:
        settings_counts.unchanged += 1
    else:
        save_settings(db, project_id, merged)
        settings_counts.updated += 1

    # ---- names the rest refers to are made to exist first, so a file that
    # mentions a skill only on a person still works
    division_names = [d.name for d in backup.divisions] + [p.division for p in backup.people]
    level_names = (
        [level.name for level in backup.levels]
        + [r.min_level for j in backup.jobs for r in j.requirements]
        + [s.level for p in backup.people for s in p.skills]
    )
    skill_names = (
        [s.name for s in backup.skills]
        + [r.skill for j in backup.jobs for r in j.requirements]
        + [s.skill for p in backup.people for s in p.skills]
    )
    divisions = ensure_divisions(db, project_id, division_names)
    levels = ensure_levels(db, project_id, level_names)
    skills = ensure_skills(db, project_id, skill_names)
    for entity, result in (("divisions", divisions), ("levels", levels), ("skills", skills)):
        counts = plan.count(entity)
        counts.created += len(result.created)
        counts.unchanged += len(result.existing)

    for division_item in backup.divisions:
        division_row = divisions.rows.get(name_key(division_item.name))
        if (
            division_row is not None
            and division_item.color
            and division_row.color != division_item.color
        ):
            division_row.color = division_item.color
    for skill in backup.skills:
        skill_row = skills.rows.get(name_key(skill.name))
        if (
            skill_row is not None
            and skill.description is not None
            and skill_row.description != skill.description
        ):
            skill_row.description = skill.description

    # ---- shift windows
    templates = _by_key(db, orm.ShiftTemplate, project_id, "name")
    counts = plan.count("shift_templates")
    for window in backup.shift_templates:
        key = name_key(window.name)
        template_row = templates.get(key)
        created = template_row is None
        if template_row is None:
            template_row = orm.ShiftTemplate(
                project_id=project_id, name=" ".join(window.name.split())
            )
            db.add(template_row)
            templates[key] = template_row
        changed = _set(
            template_row,
            start_hour=window.start_hour,
            duration_hours=window.duration_hours,
            color=window.color if window.color else template_row.color,
            is_active=True,
        )
        _tally(counts, created=created, changed=changed)
    db.flush()

    # ---- jobs
    jobs = _by_key(db, orm.Job, project_id, "name")
    counts = plan.count("jobs")
    for job_item in backup.jobs:
        missing = [n for n in job_item.shift_templates if name_key(n) not in templates]
        if missing:
            plan.problems.append(Problem("unknown_shift_window", f"{job_item.name}: {missing[0]}"))
            continue
        key = name_key(job_item.name)
        job_row = jobs.get(key)
        created = job_row is None
        if job_row is None:
            job_row = orm.Job(project_id=project_id, name=" ".join(job_item.name.split()))
            db.add(job_row)
            jobs[key] = job_row
            db.flush()
        changed = _set(
            job_row,
            required_people_per_shift=job_item.required_people_per_shift,
            division_policy=job_item.division_policy,
            priority=job_item.priority,
            is_active=True,
        )
        # A backup from before notes existed must not wipe the ones already here.
        if "notes" in job_item.model_fields_set:
            changed = _set(job_row, notes=(job_item.notes or "").strip() or None) or changed
        want_templates = sorted(templates[name_key(n)].id for n in set(job_item.shift_templates))
        have_templates = sorted(link.shift_template_id for link in job_row.shift_links)
        want_reqs = sorted(
            (
                skills.rows[name_key(r.skill)].id,
                levels.rows[name_key(r.min_level)].id,
                r.required_count or 0,
                r.is_leadership,
            )
            for r in job_item.requirements
        )
        have_reqs = sorted(
            (r.skill_id, r.min_level_id, r.required_count or 0, r.is_leadership)
            for r in job_row.requirements
        )
        if want_templates != have_templates:
            job_row.shift_links = [
                orm.JobShiftTemplate(shift_template_id=i) for i in want_templates
            ]
            changed = True
        if want_reqs != have_reqs:
            job_row.requirements = [
                orm.JobSkillRequirement(
                    skill_id=skills.rows[name_key(r.skill)].id,
                    min_level_id=levels.rows[name_key(r.min_level)].id,
                    required_count=r.required_count,
                    is_leadership=r.is_leadership,
                )
                for r in job_item.requirements
            ]
            changed = True
        _tally(counts, created=created, changed=changed)
    db.flush()

    # ---- people
    people = _by_key(db, orm.Person, project_id, "full_name")
    counts = plan.count("people")
    for person_item in backup.people:
        key = name_key(person_item.full_name)
        person_row = people.get(key)
        created = person_row is None
        if person_row is None:
            person_row = orm.Person(
                project_id=project_id,
                full_name=" ".join(person_item.full_name.split()),
                division_id=divisions.rows[name_key(person_item.division)].id,
            )
            db.add(person_row)
            people[key] = person_row
            db.flush()
        changed = _set(
            person_row,
            division_id=divisions.rows[name_key(person_item.division)].id,
            external_ref=person_item.external_ref,
            is_active=True,
        )
        want_days = sorted(set(person_item.working_weekdays))
        if want_days != sorted(d.weekday for d in person_row.working_days):
            person_row.working_days = [orm.PersonWorkingDay(weekday=d) for d in want_days]
            changed = True
        want_skills = sorted(
            (skills.rows[name_key(s.skill)].id, levels.rows[name_key(s.level)].id)
            for s in person_item.skills
        )
        if want_skills != sorted((s.skill_id, s.level_id) for s in person_row.skills):
            person_row.skills = [orm.PersonSkill(skill_id=a, level_id=b) for a, b in want_skills]
            changed = True
        _tally(counts, created=created, changed=changed)
    db.flush()

    # ---- time off: a period already on file for the person is left alone
    counts = plan.count("time_off")
    existing = {
        (t.person_id, t.start_date, t.end_date, t.start_hour, t.end_hour)
        for t in db.scalars(select(orm.TimeOff).where(orm.TimeOff.project_id == project_id))
    }
    for off in backup.time_off:
        person = people.get(name_key(off.person))
        if person is None:
            plan.problems.append(Problem("unknown_person", off.person))
            continue
        if off.end_date < off.start_date:
            plan.problems.append(Problem("bad_dates", off.person))
            continue
        if (off.start_hour is None) != (off.end_hour is None) or (
            off.start_hour is not None and off.end_hour <= off.start_hour  # type: ignore[operator]
        ):
            plan.problems.append(Problem("bad_dates", off.person))
            continue
        identity = (person.id, off.start_date, off.end_date, off.start_hour, off.end_hour)
        if identity in existing:
            counts.unchanged += 1
            continue
        db.add(
            orm.TimeOff(
                project_id=project_id,
                person_id=person.id,
                start_date=off.start_date,
                end_date=off.end_date,
                start_hour=off.start_hour,
                end_hour=off.end_hour,
                reason=off.reason,
                status=off.status,
            )
        )
        existing.add(identity)
        counts.created += 1
    db.flush()
    return plan
