"""Per-person availability tracking during a scheduling run.

There is deliberately no cap on shifts per day.  The configured rest window is
the sole governor of how often a person may work, so this state carries no
per-day counter and needs no day-boundary reset.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

from .models import EPS, Person, ShiftSlot


class PersonAvailability(NamedTuple):
    """The engine's state tuple for one person."""

    person_id: int
    available_from_hours: float
    total_shifts: int


class SchedulerState:
    def __init__(self, people: Iterable[Person], rest_period_hours: float) -> None:
        self._rest = rest_period_hours
        # Cold-start fix: seeding availability at 0.0 would block a shift that
        # begins at hour zero on day one, because the rest check would compare
        # it against the schedule's own origin.  Offsetting by a full rest
        # window makes everyone genuinely available before the horizon opens.
        self._availability: dict[int, PersonAvailability] = {
            person.id: PersonAvailability(person.id, 0.0 - rest_period_hours, 0)
            for person in people
        }

    def can_work(self, person: Person, slot: ShiftSlot) -> bool:
        if not person.is_available_on(slot.calendar_date):
            return False
        state = self._availability.get(person.id)
        if state is None:
            return False
        return state.available_from_hours <= slot.start_abs + EPS

    def commit(self, person: Person, slot: ShiftSlot) -> None:
        state = self._availability[person.id]
        self._availability[person.id] = state._replace(
            available_from_hours=slot.end_abs + self._rest,
            total_shifts=state.total_shifts + 1,
        )

    def load(self, person_id: int) -> tuple[int, float]:
        """Fairness sort key: fewest shifts so far, then longest idle."""
        state = self._availability[person_id]
        return (state.total_shifts, state.available_from_hours)

    def total_shifts(self, person_id: int) -> int:
        return self._availability[person_id].total_shifts

    def snapshot(self) -> dict[int, PersonAvailability]:
        return dict(self._availability)
