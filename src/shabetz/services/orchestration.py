"""Facade tying repository loading, the scheduling strategy and persistence."""

from __future__ import annotations

import gzip
import hashlib
import json
import secrets
import threading
from collections import OrderedDict
from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db.models import ScheduleRun
from ..domain.enums import AssignmentRole
from ..domain.models import Assignment, Job, Person, ScheduleParams
from ..repositories.db_repo import DbSchedulingRepository
from ..scheduling.greedy import SimpleGreedyScheduler
from ..scheduling.result import ScheduleResult
from ..scheduling.strategy import SchedulingStrategy
from ..setup.feasibility import FeasibilityReport, analyze
from .settings_service import SchedulingSettings, load_settings, project_today

FAIRNESS_LOOKBACK_DAYS = 28

# Parsed schedules, newest used last. Small: a schedule is tens of thousands of
# assignments at the most, and only the few currently being read matter.
PAYLOAD_CACHE_SIZE = 16
_payload_cache: OrderedDict[bytes, dict] = OrderedDict()
_payload_lock = threading.Lock()


class JobOrchestrationService:
    def __init__(
        self,
        session: DbSession,
        project_id: int,
        strategy: SchedulingStrategy | None = None,
    ) -> None:
        self._db = session
        self._project_id = project_id
        self._repo = DbSchedulingRepository(session, project_id)
        self._strategy = strategy or SimpleGreedyScheduler()

    # ------------------------------------------------------------------ loads

    def _config(self, start: date, end: date) -> tuple[list[Person], list[Job], ScheduleParams]:
        settings = load_settings(self._db, self._project_id)
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
        resolved = settings or load_settings(self._db, self._project_id)
        today = project_today(resolved)
        return analyze(
            people=self._repo.load_people(today, today),
            jobs=self._repo.load_jobs(),
            divisions=self._repo.load_divisions(),
            rest_hours=resolved.rest_period_hours,
            rotation_enabled=resolved.rotation_enabled,
        )

    # --------------------------------------------------------------- generate

    def locked_assignments(self) -> list[Assignment]:
        """Pinned shifts from the project's most recent run."""
        latest = self._db.scalars(
            select(ScheduleRun)
            .where(ScheduleRun.project_id == self._project_id)
            .order_by(ScheduleRun.created_at.desc())
            .limit(1)
        ).first()
        if latest is None:
            return []
        kept: list[Assignment] = []
        for raw in self.load_payload(latest)["assignments"]:
            if raw.get("is_locked"):
                kept.append(
                    Assignment(
                        **{
                            **raw,
                            "calendar_date": date.fromisoformat(raw["calendar_date"]),
                            "role": AssignmentRole(raw["role"]),
                        }
                    )
                )
        return kept

    def prior_load(self, start: date) -> dict[int, int]:
        """Shifts per person in the lookback before ``start``, from the published schedule."""
        published = self._db.scalars(
            select(ScheduleRun)
            .where(
                ScheduleRun.project_id == self._project_id, ScheduleRun.published_at.is_not(None)
            )
            .order_by(ScheduleRun.published_at.desc())
            .limit(1)
        ).first()
        if published is None:
            return {}
        since = (start - timedelta(days=FAIRNESS_LOOKBACK_DAYS)).isoformat()
        until = start.isoformat()
        counts: dict[int, int] = {}
        for raw in self.load_payload(published)["assignments"]:
            if since <= raw["calendar_date"] < until:
                counts[raw["person_id"]] = counts.get(raw["person_id"], 0) + 1
        return counts

    def generate(
        self, start: date, end: date, *, keep_locked: bool = False
    ) -> tuple[str, ScheduleResult, ScheduleParams]:
        people, jobs, params = self._config(start, end)
        locked = self.locked_assignments() if keep_locked else []
        carry = load_settings(self._db, self._project_id).fairness_carry_over
        result = self._strategy.generate(
            people, jobs, params, locked, self.prior_load(start) if carry else None
        )
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
            "assignments": [jsonable(asdict(a)) for a in result.assignments],
            "warnings": [jsonable(asdict(w)) for w in result.warnings],
        }
        run = ScheduleRun(
            id=schedule_id,
            project_id=self._project_id,
            created_by=created_by,
            params_json=jsonable(asdict(params)),
            summary_json=jsonable(asdict(result.summary)),
            payload_gz=gzip.compress(json.dumps(payload).encode("utf-8")),
        )
        self._db.add(run)
        self._db.flush()
        return run

    @staticmethod
    def load_payload(run: ScheduleRun) -> dict:
        """The schedule's assignments and warnings. Treat the result as read-only.

        Opening a schedule means decompressing and parsing all of it, and a
        published one is opened by every member who looks at it. Parsed copies
        are kept, keyed by a hash of the stored bytes: the same bytes can only
        ever mean the same schedule, so a hit is always right -- even after an
        edit that was rolled back.
        """
        key = hashlib.blake2b(run.payload_gz, digest_size=16).digest()
        with _payload_lock:
            hit = _payload_cache.get(key)
            if hit is not None:
                _payload_cache.move_to_end(key)
                return hit
        parsed = json.loads(gzip.decompress(run.payload_gz).decode("utf-8"))
        with _payload_lock:
            _payload_cache[key] = parsed
            while len(_payload_cache) > PAYLOAD_CACHE_SIZE:
                _payload_cache.popitem(last=False)
        return parsed


def jsonable(value: object) -> object:
    """Convert dataclass output into something the JSON column accepts."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value") and type(value).__mro__[1] is not object:
        return getattr(value, "value", value)
    return value
