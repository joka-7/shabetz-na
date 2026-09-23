"""Builders for engine tests.

Nothing here is domain vocabulary: divisions, skills and levels are invented per
test, exactly as an administrator would configure them.
"""

from __future__ import annotations

from datetime import date

from shabetz.domain.enums import DivisionPolicy
from shabetz.domain.models import (
    Job,
    Person,
    ScheduleParams,
    ShiftTemplate,
    SkillRequirement,
    TimeOffPeriod,
)

ALL_WEEKDAYS = frozenset(range(7))


def template(id: int, name: str, start_hour: float, duration: float = 8.0) -> ShiftTemplate:
    return ShiftTemplate(id=id, name=name, start_hour=start_hour, duration_hours=duration)


def three_eight_hour_blocks() -> tuple[ShiftTemplate, ...]:
    return (
        template(1, "Block A", 0.0),
        template(2, "Block B", 8.0),
        template(3, "Block C", 16.0),
    )


def requirement(
    id: int,
    skill_id: int,
    min_rank: int,
    *,
    name: str = "Skill",
    count: int | None = None,
    leadership: bool = False,
) -> SkillRequirement:
    return SkillRequirement(
        id=id,
        skill_id=skill_id,
        skill_name=name,
        min_rank=min_rank,
        required_count=count,
        is_leadership=leadership,
    )


def job(
    id: int,
    name: str,
    headcount: int,
    templates: tuple[ShiftTemplate, ...],
    requirements: tuple[SkillRequirement, ...] = (),
    policy: DivisionPolicy = DivisionPolicy.ACTIVE_DIVISION_PREFERRED,
    priority: int | None = None,
) -> Job:
    return Job(
        id=id,
        name=name,
        required_people_per_shift=headcount,
        shift_templates=templates,
        requirements=requirements,
        division_policy=policy,
        priority=priority,
    )


def person(
    id: int,
    division_id: int = 1,
    skills: dict[int, int] | None = None,
    weekdays: frozenset[int] = ALL_WEEKDAYS,
    time_off: tuple[TimeOffPeriod, ...] = (),
    name: str | None = None,
) -> Person:
    return Person(
        id=id,
        full_name=name or f"Person {id}",
        division_id=division_id,
        skill_ranks=skills or {},
        working_weekdays=weekdays,
        time_off=time_off,
    )


def roster(count: int, division_id: int = 1, skills: dict[int, int] | None = None) -> list[Person]:
    return [person(i, division_id=division_id, skills=skills) for i in range(1, count + 1)]


def params(
    start: date,
    end: date,
    *,
    rest: float = 8.0,
    rotation: bool = False,
    block_days: int = 2,
    anchor: date | None = None,
    divisions: tuple[int, ...] = (),
) -> ScheduleParams:
    return ScheduleParams(
        start_date=start,
        end_date=end,
        rest_period_hours=rest,
        rotation_enabled=rotation,
        rotation_block_days=block_days,
        rotation_anchor_date=anchor,
        division_order=divisions,
    )
