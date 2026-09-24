"""Importing a roster from a table.

The person importing chooses what each column means; this module checks every
row against the current configuration and reports, row by row, what would
happen. The same call then applies it. Nothing is written unless asked, so the
preview and the import can never disagree about what a row means.

Rows with a problem are reported and skipped; the rest still import. A person
whose name already exists is left untouched rather than duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as orm
from .catalog import ensure_divisions, ensure_skills, name_key
from .days import DaysError, parse_weekdays

ColumnRole = Literal["name", "division", "days", "skill", "ignore"]
RowStatus = Literal["create", "exists", "error"]

MAX_NAME_LENGTH = 160
MAX_GROUP_NAME_LENGTH = 120

# A tick in a skill column means "has it" when no level is named: the lowest
# rung of the ladder.
_MARKS = {"x", "v", "✓", "✔", "✅", "+", "*", "yes", "y", "true", "כן", "יש"}
_BLANKS = {"", "-", "–", "no", "n", "false", "0", "לא", "אין"}


@dataclass(frozen=True)
class Column:
    role: ColumnRole
    skill_name: str | None = None


@dataclass
class Problem:
    code: str
    value: str | None = None


@dataclass
class RowPlan:
    line: int
    full_name: str
    division: str | None
    status: RowStatus
    working_weekdays: list[int] = field(default_factory=list)
    skills: dict[str, str] = field(default_factory=dict)  # skill name -> level name
    problems: list[Problem] = field(default_factory=list)


@dataclass
class ImportPlan:
    rows: list[RowPlan]
    new_divisions: list[str]
    new_skills: list[str]
    applied: bool = False

    @property
    def to_create(self) -> int:
        return sum(1 for row in self.rows if row.status == "create")


class ImportRequestError(ValueError):
    """The request itself is unusable, as opposed to one of its rows."""


def _cell(row: list[str], index: int) -> str:
    return " ".join(row[index].split()) if index < len(row) else ""


def plan_people_import(
    db: Session,
    project_id: int,
    columns: list[Column],
    rows: list[list[str]],
    default_division_id: int | None,
    default_weekdays: list[int],
) -> ImportPlan:
    name_columns = [i for i, c in enumerate(columns) if c.role == "name"]
    if len(name_columns) != 1:
        raise ImportRequestError("Choose exactly one column holding the names")
    name_at = name_columns[0]
    division_at = next((i for i, c in enumerate(columns) if c.role == "division"), None)
    days_at = next((i for i, c in enumerate(columns) if c.role == "days"), None)
    skill_columns = [
        (i, " ".join((c.skill_name or "").split()))
        for i, c in enumerate(columns)
        if c.role == "skill" and (c.skill_name or "").strip()
    ]

    divisions = {
        name_key(d.name): d.name
        for d in db.scalars(
            select(orm.Division).where(
                orm.Division.project_id == project_id, orm.Division.is_active.is_(True)
            )
        )
    }
    default_division = None
    if default_division_id is not None:
        found = db.get(orm.Division, default_division_id)
        if found is None or not found.is_active or found.project_id != project_id:
            raise ImportRequestError(f"Division {default_division_id} does not exist")
        default_division = found.name

    skills = {
        name_key(s.name): s.name
        for s in db.scalars(
            select(orm.Skill).where(
                orm.Skill.project_id == project_id, orm.Skill.is_active.is_(True)
            )
        )
    }
    levels = list(
        db.scalars(
            select(orm.ProficiencyLevel)
            .where(
                orm.ProficiencyLevel.project_id == project_id,
                orm.ProficiencyLevel.is_active.is_(True),
            )
            .order_by(orm.ProficiencyLevel.rank)
        )
    )
    level_names = {name_key(level.name): level.name for level in levels}

    existing_people = {
        name_key(p.full_name)
        for p in db.scalars(
            select(orm.Person).where(
                orm.Person.project_id == project_id, orm.Person.is_active.is_(True)
            )
        )
    }
    seen_in_file: set[str] = set()
    new_divisions: dict[str, str] = {}
    new_skills: dict[str, str] = {}
    plans: list[RowPlan] = []

    for line, raw in enumerate(rows, start=1):
        full_name = _cell(raw, name_at)
        if not full_name and not any(cell.strip() for cell in raw):
            continue  # a blank row is not worth reporting
        problems: list[Problem] = []

        if not full_name:
            problems.append(Problem("missing_name"))
        elif len(full_name) > MAX_NAME_LENGTH:
            problems.append(Problem("name_too_long", full_name[:40]))

        division = _cell(raw, division_at) if division_at is not None else ""
        if len(division) > MAX_GROUP_NAME_LENGTH:
            problems.append(Problem("name_too_long", division[:40]))
        elif division:
            division = divisions.get(name_key(division)) or new_divisions.setdefault(
                name_key(division), division
            )
        elif default_division:
            division = default_division
        else:
            problems.append(Problem("missing_division"))

        weekdays = sorted(set(default_weekdays))
        days_text = _cell(raw, days_at) if days_at is not None else ""
        if days_text:
            try:
                weekdays = parse_weekdays(days_text)
            except DaysError:
                problems.append(Problem("bad_days", days_text))

        person_skills: dict[str, str] = {}
        for index, skill_name in skill_columns:
            value = _cell(raw, index)
            if value.casefold() in _BLANKS:
                continue
            if not levels:
                problems.append(Problem("no_levels", value))
                continue
            level = level_names.get(name_key(value))
            if level is None and value.casefold() in _MARKS:
                level = levels[0].name
            if level is None:
                problems.append(Problem("unknown_level", value))
                continue
            skill = skills.get(name_key(skill_name)) or new_skills.setdefault(
                name_key(skill_name), skill_name
            )
            person_skills[skill] = level

        key = name_key(full_name)
        status: RowStatus = "create"
        if problems:
            status = "error"
        elif key in existing_people:
            status = "exists"
        elif key in seen_in_file:
            status = "error"
            problems.append(Problem("duplicate_in_file", full_name))
        if full_name:
            seen_in_file.add(key)

        plans.append(
            RowPlan(
                line=line,
                full_name=full_name,
                division=division or None,
                status=status,
                working_weekdays=weekdays,
                skills=person_skills,
                problems=problems,
            )
        )

    # Only what a row that will actually be imported needs gets created.
    importing = [p for p in plans if p.status == "create"]
    wanted_divisions = {name_key(p.division) for p in importing if p.division}
    wanted_skills = {name_key(s) for p in importing for s in p.skills}
    return ImportPlan(
        rows=plans,
        new_divisions=[n for k, n in new_divisions.items() if k in wanted_divisions],
        new_skills=[n for k, n in new_skills.items() if k in wanted_skills],
    )


def apply_people_import(db: Session, project_id: int, plan: ImportPlan) -> list[orm.Person]:
    importing = [row for row in plan.rows if row.status == "create"]
    divisions = ensure_divisions(
        db, project_id, [row.division for row in importing if row.division]
    )
    skills = ensure_skills(db, project_id, [skill for row in importing for skill in row.skills])
    levels = {
        name_key(level.name): level
        for level in db.scalars(
            select(orm.ProficiencyLevel).where(
                orm.ProficiencyLevel.project_id == project_id,
                orm.ProficiencyLevel.is_active.is_(True),
            )
        )
    }

    created: list[orm.Person] = []
    for row in importing:
        assert row.division is not None  # rows without one are errors
        person = orm.Person(
            project_id=project_id,
            full_name=row.full_name,
            division_id=divisions.rows[name_key(row.division)].id,
        )
        person.working_days = [orm.PersonWorkingDay(weekday=d) for d in row.working_weekdays]
        person.skills = [
            orm.PersonSkill(
                skill_id=skills.rows[name_key(skill)].id,
                level_id=levels[name_key(level)].id,
            )
            for skill, level in row.skills.items()
        ]
        db.add(person)
        created.append(person)
    db.flush()
    plan.applied = True
    return created
