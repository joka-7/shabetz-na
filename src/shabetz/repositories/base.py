"""Repository abstraction.

Keeping this abstract means the scheduling service never learns where
configuration comes from, which is what lets the engine be tested against
literals with no database at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..domain.models import Division, Job, Person


class JobSchedulingRepository(ABC):
    @abstractmethod
    def load_divisions(self) -> list[Division]:
        raise NotImplementedError

    @abstractmethod
    def load_people(self, window_start: date, window_end: date) -> list[Person]:
        raise NotImplementedError

    @abstractmethod
    def load_jobs(self) -> list[Job]:
        raise NotImplementedError
