"""The scheduling strategy interface.

Keeping this abstract lets the assignment algorithm be swapped without touching
the service, repository or API layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from ..domain.models import Assignment, Job, Person, ScheduleParams
from .result import ScheduleResult


class SchedulingStrategy(ABC):
    @abstractmethod
    def generate(
        self,
        people: Sequence[Person],
        jobs: Sequence[Job],
        params: ScheduleParams,
        locked: Sequence[Assignment] = (),
        prior_load: Mapping[int, int] | None = None,
    ) -> ScheduleResult:
        """Produce assignments for every shift in the parameter window.

        ``locked`` are assignments a person pinned; they are kept as they are
        and the rest of the schedule is built around them. ``prior_load`` is
        how many shifts each person worked just before the window, so fairness
        carries on from the last schedule instead of starting from zero.
        """
        raise NotImplementedError
