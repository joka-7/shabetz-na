"""Facade tying repository loading, the scheduling strategy and persistence."""

from __future__ import annotations

import gzip
import json
import secrets
from dataclasses import asdict
from datetime import date

from sqlalchemy.orm import Session as DbSession

from ..db.models import ScheduleRun
from ..domain.models import Job, Person, ScheduleParams
from ..repositories.db_repo import DbSchedulingRepository
from ..scheduling.greedy import SimpleGreedyScheduler
from ..scheduling.result import ScheduleResult
from ..scheduling.strategy import SchedulingStrategy
from ..setup.feasibility import FeasibilityReport, analyze
from .settings_service import SchedulingSettings, load_settings


class JobOrchestrationService:
    def __init__(
        self, session: DbSession, strategy: SchedulingStrategy | None = None
    ) -> None:
        self._db = session
        self._repo = DbSchedulingRepository(session)
        self._strategy = strategy or SimpleGreedyScheduler()

    # ------------------------------------------------------------------ loads

    def _config(self, start: date, end: date) -> tuple[list[Person], list[Job], ScheduleParams]:
        settings = load_settings(self._db)
        divisions = self._repo.load_divisions()
        people = self._repo.load_people(start, end)
        jobs = self._repo.load_jobs()
        params = ScheduleParams(
            start_date=start,
            end_date=end,
            rest_period_hours=settings.rest_period_hours,
            rotation_enabled=settings.rotation_enabled,
            rotation_block_days=settings.rotation_block_days,
            # Persisting the anchor keeps duty stable when a later window is
            # regenerated; defaulting it to the start date would silently shift
            # which division is on duty.
            rotation_anchor_date=settings.rotation_anchor_date or start,
            division_order=tuple(d.id for d in divisions),
        )
        return people, jobs, params

    # --------------------------------------------------------------- analysis

    def feasibility(self, settings: SchedulingSettings | None = None) -> FeasibilityReport:
        resolved = settings or load_settings(self._db)
        today = date.today()
        return analyze(
            people=self._repo.load_people(today, today),
            jobs=self._repo.load_jobs(),
            divisions=self._repo.load_divisions(),
            rest_hours=resolved.rest_period_hours,
            rotation_enabled=resolved.rotation_enabled,
        )

    # --------------------------------------------------------------- generate

    def generate(self, start: date, end: date) -> tuple[str, ScheduleResult, ScheduleParams]:
        people, jobs, params = self._config(start, end)
        result = self._strategy.generate(people, jobs, params)
        schedule_id = secrets.token_urlsafe(16)
        return schedule_id, result, params

    def persist(
        self,
        schedule_id: str,
        result: ScheduleResult,
        params: ScheduleParams,
        created_by: int | None,
    ) -> ScheduleRun:
        payload = {
            "assignments": [_jsonable(asdict(a)) for a in result.assignments],
            "warnings": [_jsonable(asdict(w)) for w in result.warnings],
        }
        run = ScheduleRun(
            id=schedule_id,
            created_by=created_by,
            params_json=_jsonable(asdict(params)),
            summary_json=_jsonable(asdict(result.summary)),
            payload_gz=gzip.compress(json.dumps(payload).encode("utf-8")),
        )
        self._db.add(run)
        self._db.flush()
        return run

    @staticmethod
    def load_payload(run: ScheduleRun) -> dict:
        return json.loads(gzip.decompress(run.payload_gz).decode("utf-8"))


def _jsonable(value: object) -> object:
    """Convert dataclass output into something the JSON column accepts."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value") and type(value).__mro__[1] is not object:
        return getattr(value, "value", value)
    return value
