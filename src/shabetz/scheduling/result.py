"""The output of a scheduling run."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from ..domain.enums import WarningSeverity
from ..domain.models import Assignment, Person, ScheduleParams, ScheduleWarning


@dataclass(frozen=True, slots=True)
class ScheduleSummary:
    total_assignments: int
    total_people: int
    people_used: int
    utilization_rate: float
    understaffed_shift_count: int
    division_fallback_count: int
    active_division_by_day: dict[str, int | None] = field(default_factory=dict)
    shifts_per_division: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    assignments: tuple[Assignment, ...]
    warnings: tuple[ScheduleWarning, ...]
    summary: ScheduleSummary

    @property
    def blocking_warnings(self) -> tuple[ScheduleWarning, ...]:
        """Warnings an operator must act on; division fallbacks are informational."""
        return tuple(
            w
            for w in self.warnings
            if w.severity in (WarningSeverity.ERROR, WarningSeverity.WARNING)
        )


def build_summary(
    assignments: tuple[Assignment, ...],
    warnings: tuple[ScheduleWarning, ...],
    people: tuple[Person, ...],
    params: ScheduleParams,
    active_by_day: dict[date, int | None],
) -> ScheduleSummary:
    people_used = {a.person_id for a in assignments}
    shifts_per_division: dict[int, int] = defaultdict(int)
    for assignment in assignments:
        shifts_per_division[assignment.division_id] += 1

    understaffed = sum(1 for w in warnings if w.severity is WarningSeverity.ERROR)
    fallbacks = sum(1 for a in assignments if a.is_division_fallback)

    return ScheduleSummary(
        total_assignments=len(assignments),
        total_people=len(people),
        people_used=len(people_used),
        utilization_rate=(len(people_used) / len(people)) if people else 0.0,
        understaffed_shift_count=understaffed,
        division_fallback_count=fallbacks,
        active_division_by_day={d.isoformat(): v for d, v in sorted(active_by_day.items())},
        shifts_per_division=dict(shifts_per_division),
    )
