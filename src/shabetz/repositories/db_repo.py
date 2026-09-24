"""Loads a project's configuration out of the database into the engine's domain objects."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import models as orm
from ..domain.enums import TimeOffStatus
from ..domain.models import (
    Division,
    Job,
    Person,
    ShiftTemplate,
    SkillRequirement,
    TimeOffPeriod,
)
from .base import JobSchedulingRepository


class DbSchedulingRepository(JobSchedulingRepository):
    """Reads one project's configuration; nothing from another project."""

    def __init__(self, session: Session, project_id: int) -> None:
        self._session = session
        self._project_id = project_id

    def load_divisions(self) -> list[Division]:
        rows = self._session.scalars(
            select(orm.Division)
            .where(orm.Division.project_id == self._project_id, orm.Division.is_active.is_(True))
            .order_by(orm.Division.display_order, orm.Division.id)
        ).all()
        return [Division(id=r.id, name=r.name, display_order=r.display_order) for r in rows]

    def load_people(self, window_start: date, window_end: date) -> list[Person]:
        rows = self._session.scalars(
            select(orm.Person)
            .where(orm.Person.project_id == self._project_id, orm.Person.is_active.is_(True))
            .options(
                selectinload(orm.Person.skills).selectinload(orm.PersonSkill.level),
                selectinload(orm.Person.working_days),
                selectinload(orm.Person.time_off),
            )
            .order_by(orm.Person.id)
        ).all()

        people: list[Person] = []
        for row in rows:
            # Only approved absence removes someone from the roster; a pending
            # request must never quietly change a schedule.
            absences = tuple(
                TimeOffPeriod(start_date=t.start_date, end_date=t.end_date)
                for t in row.time_off
                if t.status is TimeOffStatus.APPROVED
                and t.end_date >= window_start
                and t.start_date <= window_end
            )
            people.append(
                Person(
                    id=row.id,
                    full_name=row.full_name,
                    division_id=row.division_id,
                    skill_ranks={s.skill_id: s.level.rank for s in row.skills},
                    working_weekdays=frozenset(d.weekday for d in row.working_days),
                    time_off=absences,
                )
            )
        return people

    def load_jobs(self) -> list[Job]:
        rows = self._session.scalars(
            select(orm.Job)
            .where(orm.Job.project_id == self._project_id, orm.Job.is_active.is_(True))
            .options(
                selectinload(orm.Job.shift_links).selectinload(orm.JobShiftTemplate.shift_template),
                selectinload(orm.Job.requirements).selectinload(orm.JobSkillRequirement.skill),
                selectinload(orm.Job.requirements).selectinload(orm.JobSkillRequirement.min_level),
            )
            .order_by(orm.Job.id)
        ).all()

        jobs: list[Job] = []
        for row in rows:
            templates = tuple(
                ShiftTemplate(
                    id=link.shift_template.id,
                    name=link.shift_template.name,
                    start_hour=link.shift_template.start_hour,
                    duration_hours=link.shift_template.duration_hours,
                )
                for link in sorted(row.shift_links, key=lambda link: link.shift_template.start_hour)
                if link.shift_template.is_active
            )
            requirements = tuple(
                SkillRequirement(
                    id=req.id,
                    skill_id=req.skill_id,
                    skill_name=req.skill.name,
                    min_rank=req.min_level.rank,
                    required_count=req.required_count,
                    is_leadership=req.is_leadership,
                )
                for req in sorted(row.requirements, key=lambda r: r.id)
            )
            jobs.append(
                Job(
                    id=row.id,
                    name=row.name,
                    required_people_per_shift=row.required_people_per_shift,
                    shift_templates=templates,
                    requirements=requirements,
                    division_policy=row.division_policy,
                    priority=row.priority,
                )
            )
        return jobs
