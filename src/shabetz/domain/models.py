"""Configuration snapshots the scheduling engine operates on.

These are plain frozen dataclasses mapped from database rows by the repository
layer.  The engine never sees SQLAlchemy, so it can be exercised in tests with
literals and no database at all.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from .enums import AssignmentRole, DivisionPolicy, WarningKind, WarningSeverity

EPS = 1e-6
"""Float tolerance for hour comparisons; rest windows are never sub-second."""

HOURS_PER_DAY = 24.0


class InvalidConfiguration(ValueError):
    """Raised when configuration cannot produce a well-formed schedule."""


@dataclass(frozen=True, slots=True)
class Division:
    id: int
    name: str
    display_order: int


@dataclass(frozen=True, slots=True)
class ProficiencyLevel:
    id: int
    name: str
    rank: int


@dataclass(frozen=True, slots=True)
class ShiftTemplate:
    """An admin-defined working window.

    ``start_hour`` and ``duration_hours`` are arbitrary, so a template may start
    at any time of day and may run past midnight.
    """

    id: int
    name: str
    start_hour: float
    duration_hours: float

    def __post_init__(self) -> None:
        if self.duration_hours <= 0:
            raise InvalidConfiguration(
                f"Shift template {self.name!r} must have a positive duration"
            )
        if not 0.0 <= self.start_hour < HOURS_PER_DAY:
            raise InvalidConfiguration(
                f"Shift template {self.name!r} start hour must be within [0, 24)"
            )


@dataclass(frozen=True, slots=True)
class SkillRequirement:
    """A staffing prerequisite on a job.

    ``required_count`` of ``None`` means *every* person on the shift must meet
    it.  An integer means *at least that many* must, which is how the mandatory
    leadership role is expressed without hardcoding a single leadership slot.
    """

    id: int
    skill_id: int
    skill_name: str
    min_rank: int
    required_count: int | None = None
    is_leadership: bool = False

    @property
    def applies_to_all(self) -> bool:
        return self.required_count is None


@dataclass(frozen=True, slots=True)
class Job:
    id: int
    name: str
    required_people_per_shift: int
    shift_templates: tuple[ShiftTemplate, ...]
    requirements: tuple[SkillRequirement, ...] = ()
    division_policy: DivisionPolicy = DivisionPolicy.ACTIVE_DIVISION_PREFERRED
    priority: int | None = None

    def __post_init__(self) -> None:
        if self.required_people_per_shift < 1:
            raise InvalidConfiguration(f"Job {self.name!r} must require at least one person")

    @property
    def shift_count(self) -> int:
        """How many slots this job produces per day.

        The spec derived this as ``daily_coverage_hours / shift_duration_hours``.
        With admin-defined templates it is simply how many windows are attached,
        which also permits uneven and overlapping coverage.
        """
        return len(self.shift_templates)

    @property
    def role_requirements(self) -> tuple[SkillRequirement, ...]:
        """Requirements a specific number of people must satisfy (phase 1)."""
        return tuple(r for r in self.requirements if not r.applies_to_all)

    @property
    def blanket_requirements(self) -> tuple[SkillRequirement, ...]:
        """Requirements every person on the shift must satisfy (phase 2)."""
        return tuple(r for r in self.requirements if r.applies_to_all)

    @property
    def constraint_weight(self) -> int:
        """How demanding this job's requirements are, weighted by level rank.

        Used to order jobs so scarce, highly-skilled work is staffed before
        general labour pools drain the roster.
        """
        return sum(r.min_rank + 1 for r in self.requirements)

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        """Starvation-prevention ordering.

        Low-frequency jobs first, then the most constrained.  The trailing
        ``id`` is not cosmetic: without it ``sorted`` is merely stable, so the
        result would depend on row insertion order and runs would stop being
        reproducible.
        """
        return (
            self.priority if self.priority is not None else 0,
            self.shift_count,
            -self.constraint_weight,
            self.id,
        )


@dataclass(frozen=True, slots=True)
class TimeOffPeriod:
    """An approved absence.  Both endpoints are inclusive."""

    start_date: date
    end_date: date

    def covers(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date


@dataclass(frozen=True, slots=True)
class Person:
    id: int
    full_name: str
    division_id: int
    skill_ranks: Mapping[int, int] = field(default_factory=dict)
    working_weekdays: frozenset[int] = field(default_factory=frozenset)
    time_off: tuple[TimeOffPeriod, ...] = ()

    def meets(self, requirement: SkillRequirement) -> bool:
        """Whether this person holds the skill at or above the required rank.

        Comparison is by ``rank``, never by level name, so administrators may
        name and reorder the proficiency ladder freely.
        """
        rank = self.skill_ranks.get(requirement.skill_id)
        return rank is not None and rank >= requirement.min_rank

    def meets_all(self, requirements: Sequence[SkillRequirement]) -> bool:
        return all(self.meets(r) for r in requirements)

    def is_available_on(self, day: date) -> bool:
        if day.weekday() not in self.working_weekdays:
            return False
        return not any(period.covers(day) for period in self.time_off)


@dataclass(frozen=True, slots=True)
class ShiftSlot:
    """One instance of a job's shift template on a particular day.

    Times are absolute hours since the schedule's first midnight.  Because that
    value increases monotonically across the whole horizon, crossing midnight
    needs no special handling; modulo-24 arithmetic appears only where a slot is
    displayed.
    """

    job_id: int
    job_name: str
    template_id: int
    template_name: str
    calendar_date: date
    day_index: int
    start_abs: float
    duration_hours: float

    @classmethod
    def build(
        cls, job: Job, template: ShiftTemplate, day: date, day_index: int
    ) -> ShiftSlot:
        return cls(
            job_id=job.id,
            job_name=job.name,
            template_id=template.id,
            template_name=template.name,
            calendar_date=day,
            day_index=day_index,
            start_abs=day_index * HOURS_PER_DAY + template.start_hour,
            duration_hours=template.duration_hours,
        )

    @property
    def end_abs(self) -> float:
        return self.start_abs + self.duration_hours

    @property
    def clock_start(self) -> float:
        return self.start_abs % HOURS_PER_DAY

    @property
    def clock_end(self) -> float:
        return self.end_abs % HOURS_PER_DAY

    @property
    def crosses_midnight(self) -> bool:
        """True when the slot ends on a later calendar day.

        A window ending exactly at midnight does not count as crossing.
        """
        start_day = math.floor(self.start_abs / HOURS_PER_DAY + EPS)
        end_day = math.ceil(self.end_abs / HOURS_PER_DAY - EPS) - 1
        return end_day > start_day

    @property
    def end_calendar_date(self) -> date:
        end_day_index = math.ceil(self.end_abs / HOURS_PER_DAY - EPS) - 1
        return self.calendar_date + timedelta(days=end_day_index - self.day_index)

    def overlaps(self, other: ShiftSlot) -> bool:
        return self.start_abs < other.end_abs - EPS and other.start_abs < self.end_abs - EPS


@dataclass(frozen=True, slots=True)
class Assignment:
    person_id: int
    person_name: str
    division_id: int
    job_id: int
    job_name: str
    template_id: int
    template_name: str
    calendar_date: date
    start_abs: float
    end_abs: float
    role: AssignmentRole
    is_division_fallback: bool
    satisfied_requirement_id: int | None = None


@dataclass(frozen=True, slots=True)
class ScheduleWarning:
    kind: WarningKind
    severity: WarningSeverity
    message: str
    calendar_date: date | None = None
    job_id: int | None = None
    template_id: int | None = None
    required: int | None = None
    assigned: int | None = None


@dataclass(frozen=True, slots=True)
class ScheduleParams:
    """Everything the engine needs beyond the roster and the jobs."""

    start_date: date
    end_date: date
    rest_period_hours: float = 8.0
    rotation_enabled: bool = True
    rotation_block_days: int = 2
    rotation_anchor_date: date | None = None
    division_order: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise InvalidConfiguration("End date must not precede start date")
        if self.rest_period_hours < 0:
            raise InvalidConfiguration("Rest period must not be negative")
        if self.rotation_block_days < 1:
            raise InvalidConfiguration("Rotation block must span at least one day")

    @property
    def anchor(self) -> date:
        return self.rotation_anchor_date or self.start_date
