"""Hand edits to a generated schedule.

The engine proposes; a person decides. An administrator or collaborator can
swap who works a shift, add someone, or take someone off, after the fact.

Edits are allowed to break the engine's own rules -- the point of an override
is that a human knows something the rules do not -- but never silently. Every
proposed change is checked first and its conflicts are reported; the caller
must acknowledge them before the change is saved, and conflicts that were
accepted stay on the schedule as warnings.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta

from sqlalchemy.orm import Session as DbSession

from ..db.models import ScheduleRun
from ..domain.enums import AssignmentRole, WarningKind, WarningSeverity
from ..domain.models import (
    EPS,
    Assignment,
    Job,
    Person,
    ScheduleWarning,
    ShiftSlot,
)
from ..repositories.db_repo import DbSchedulingRepository
from ..scheduling.warnings import slot_warnings
from .orchestration import JobOrchestrationService, jsonable


class EditError(Exception):
    """The edit cannot be made at all, as opposed to made with conflicts."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class SlotKey:
    job_id: int
    template_id: int
    calendar_date: date


@dataclass(frozen=True, slots=True)
class Conflict:
    kind: WarningKind
    person_id: int
    person_name: str
    message: str


def _assignment(raw: dict) -> Assignment:
    return Assignment(
        **{
            **raw,
            "calendar_date": date.fromisoformat(raw["calendar_date"]),
            "role": AssignmentRole(raw["role"]),
        }
    )


def _key(a: Assignment) -> SlotKey:
    return SlotKey(a.job_id, a.template_id, a.calendar_date)


class ScheduleEditor:
    def __init__(self, db: DbSession, project_id: int, run: ScheduleRun) -> None:
        self._db = db
        self._run = run
        params = run.params_json
        self._start = date.fromisoformat(params["start_date"])
        self._end = date.fromisoformat(params["end_date"])
        self._rest = float(params.get("rest_period_hours", 0.0))

        repo = DbSchedulingRepository(db, project_id)
        self._people: dict[int, Person] = {
            p.id: p for p in repo.load_people(self._start, self._end)
        }
        self._jobs: dict[int, Job] = {j.id: j for j in repo.load_jobs()}

        payload = JobOrchestrationService.load_payload(run)
        self.assignments: list[Assignment] = [_assignment(a) for a in payload["assignments"]]

    # ---------------------------------------------------------------- lookups

    def _slot(self, key: SlotKey) -> ShiftSlot:
        job = self._jobs.get(key.job_id)
        if job is None:
            raise EditError("NOT_FOUND", "Job not found")
        template = next((t for t in job.shift_templates if t.id == key.template_id), None)
        if template is None:
            raise EditError("NOT_FOUND", "That job does not use this shift window")
        if not self._start <= key.calendar_date <= self._end:
            raise EditError("INVALID_CONFIGURATION", "That date is outside this schedule")
        return ShiftSlot.build(
            job, template, key.calendar_date, (key.calendar_date - self._start).days
        )

    def _person(self, person_id: int) -> Person:
        person = self._people.get(person_id)
        if person is None:
            raise EditError("NOT_FOUND", "Person not found")
        return person

    @property
    def run(self) -> ScheduleRun:
        return self._run

    def find(self, key: SlotKey, person_id: int) -> Assignment:
        return self.assignments[self._index_of(key, person_id)]

    def _index_of(self, key: SlotKey, person_id: int) -> int:
        for index, a in enumerate(self.assignments):
            if _key(a) == key and a.person_id == person_id:
                return index
        raise EditError("NOT_FOUND", "That person is not assigned to this shift")

    # -------------------------------------------------------------- conflicts

    def conflicts_for(
        self,
        person_id: int,
        key: SlotKey,
        *,
        ignore: Assignment | None = None,
        requirement_id: int | None = None,
    ) -> list[Conflict]:
        """Rules this person would break by working this slot.

        ``ignore`` is the assignment being replaced, which must not count
        against its own replacement.
        """
        person = self._person(person_id)
        slot = self._slot(key)
        job = self._jobs[key.job_id]
        name = person.full_name
        found: list[Conflict] = []

        def add(kind: WarningKind, message: str) -> None:
            found.append(Conflict(kind, person.id, name, message))

        where = f"{job.name} on {key.calendar_date.isoformat()} ({slot.template_name})"

        if not person.is_available_on(key.calendar_date):
            add(
                WarningKind.UNAVAILABLE,
                f"{name} is not available on {key.calendar_date.isoformat()}"
                " (day off or approved time off)",
            )

        needed = list(job.blanket_requirements)
        if requirement_id is not None:
            needed += [r for r in job.requirements if r.id == requirement_id]
        if not person.meets_all(needed):
            add(
                WarningKind.MISSING_SKILL,
                f"{name} does not meet the skill requirements for {job.name}",
            )

        overlapping = too_close = False
        for other in self.assignments:
            if other.person_id != person_id or other is ignore:
                continue
            if _key(other) == key:
                continue
            start, end = other.start_abs, other.end_abs
            if slot.start_abs < end - EPS and start < slot.end_abs - EPS:
                overlapping = True
            elif (
                0 <= slot.start_abs - end < self._rest - EPS
                or 0 <= start - slot.end_abs < self._rest - EPS
            ):
                too_close = True
        if overlapping:
            add(WarningKind.DOUBLE_BOOKED, f"{name} is already on an overlapping shift for {where}")
        if too_close:
            add(
                WarningKind.REST_VIOLATION, f"{name} would not get the required rest around {where}"
            )
        return found

    def suggest(
        self, key: SlotKey, *, replaces_person_id: int | None = None, limit: int = 8
    ) -> list[tuple[Person, list[Conflict], int]]:
        """Who could work this slot, cleanest first.

        Ordered by fewest broken rules, then fewest shifts already held in this
        schedule, so a gap is offered to whoever can cover it most fairly.
        """
        self._slot(key)
        ignore = self.find(key, replaces_person_id) if replaces_person_id is not None else None
        requirement_id = ignore.satisfied_requirement_id if ignore else None
        on_slot = {a.person_id for a in self.assignments if _key(a) == key}
        load: dict[int, int] = defaultdict(int)
        for a in self.assignments:
            load[a.person_id] += 1

        ranked = []
        for person in self._people.values():
            if person.id in on_slot:
                continue
            found = self.conflicts_for(person.id, key, ignore=ignore, requirement_id=requirement_id)
            ranked.append((person, found, load[person.id]))
        ranked.sort(key=lambda r: (len(r[1]), r[2], r[0].id))
        return ranked[:limit]

    # ------------------------------------------------------------------ edits

    def reassign(self, key: SlotKey, from_person_id: int, to_person_id: int) -> list[Conflict]:
        index = self._index_of(key, from_person_id)
        old = self.assignments[index]
        if from_person_id == to_person_id:
            raise EditError("INVALID_CONFIGURATION", "Choose a different person")
        if any(_key(a) == key and a.person_id == to_person_id for a in self.assignments):
            raise EditError("CONFLICT", "That person is already on this shift")
        conflicts = self.conflicts_for(
            to_person_id, key, ignore=old, requirement_id=old.satisfied_requirement_id
        )
        person = self._person(to_person_id)
        self.assignments[index] = Assignment(
            person_id=person.id,
            person_name=person.full_name,
            division_id=person.division_id,
            job_id=old.job_id,
            job_name=old.job_name,
            template_id=old.template_id,
            template_name=old.template_name,
            calendar_date=old.calendar_date,
            start_abs=old.start_abs,
            end_abs=old.end_abs,
            role=old.role,
            is_division_fallback=False,
            satisfied_requirement_id=old.satisfied_requirement_id,
            is_manual=True,
            is_locked=True,
        )
        return conflicts

    def add(self, key: SlotKey, person_id: int) -> list[Conflict]:
        slot = self._slot(key)
        if any(_key(a) == key and a.person_id == person_id for a in self.assignments):
            raise EditError("CONFLICT", "That person is already on this shift")
        conflicts = self.conflicts_for(person_id, key)
        person = self._person(person_id)
        self.assignments.append(
            Assignment(
                person_id=person.id,
                person_name=person.full_name,
                division_id=person.division_id,
                job_id=slot.job_id,
                job_name=slot.job_name,
                template_id=slot.template_id,
                template_name=slot.template_name,
                calendar_date=slot.calendar_date,
                start_abs=slot.start_abs,
                end_abs=slot.end_abs,
                role=AssignmentRole.MEMBER,
                is_division_fallback=False,
                satisfied_requirement_id=None,
                is_manual=True,
                is_locked=True,
            )
        )
        self.assignments.sort(key=lambda a: a.calendar_date)
        return conflicts

    def snapshot(self, key: SlotKey, person_id: int) -> dict:
        """The stored form of one assignment, for the history and for undo."""
        return jsonable(asdict(self.find(key, person_id)))  # type: ignore[return-value]

    def restore(self, before: dict | None, after: dict | None) -> None:
        """Put one assignment back as it was, without re-checking any rule.

        ``after`` is what the edit left behind and ``before`` what it replaced;
        either may be absent (an add has no before, a removal no after).
        """
        if after is not None:
            now = _assignment(after)
            del self.assignments[self._index_of(_key(now), now.person_id)]
        if before is not None:
            self.assignments.append(_assignment(before))
            self.assignments.sort(key=lambda a: a.calendar_date)

    def set_lock(self, key: SlotKey, person_id: int, locked: bool) -> None:
        index = self._index_of(key, person_id)
        self.assignments[index] = replace(self.assignments[index], is_locked=locked)

    def remove(self, key: SlotKey, person_id: int) -> None:
        del self.assignments[self._index_of(key, person_id)]

    # ------------------------------------------------------------------- save

    def save(self) -> None:
        warnings = self._recompute_warnings()
        payload = {
            "assignments": [jsonable(asdict(a)) for a in self.assignments],
            "warnings": [jsonable(asdict(w)) for w in warnings],
        }
        self._run.payload_gz = gzip.compress(json.dumps(payload).encode("utf-8"))
        self._run.summary_json = self._recompute_summary(warnings)
        self._db.flush()

    def _recompute_warnings(self) -> list[ScheduleWarning]:
        by_slot: dict[SlotKey, list[Assignment]] = defaultdict(list)
        for a in self.assignments:
            by_slot[_key(a)].append(a)

        warnings: list[ScheduleWarning] = []
        # Same walk as the engine, so an edited run words its gaps the same way.
        ordered = sorted(self._jobs.values(), key=lambda j: j.sort_key)
        day, index = self._start, 0
        while day <= self._end:
            for job in ordered:
                for template in job.shift_templates:
                    slot = ShiftSlot.build(job, template, day, index)
                    picked = by_slot.get(SlotKey(job.id, template.id, day), [])
                    warnings.extend(slot_warnings(job, slot, picked))
            day += timedelta(days=1)
            index += 1

        for a in self.assignments:
            if not a.is_manual or a.job_id not in self._jobs:
                continue
            for conflict in self.conflicts_for(
                a.person_id, _key(a), ignore=a, requirement_id=a.satisfied_requirement_id
            ):
                warnings.append(
                    ScheduleWarning(
                        kind=conflict.kind,
                        severity=WarningSeverity.WARNING,
                        message=conflict.message,
                        calendar_date=a.calendar_date,
                        job_id=a.job_id,
                        template_id=a.template_id,
                        job_name=a.job_name,
                        template_name=a.template_name,
                        person_name=a.person_name,
                    )
                )
        return warnings

    def _recompute_summary(self, warnings: list[ScheduleWarning]) -> dict:
        summary = dict(self._run.summary_json)
        people_used = {a.person_id for a in self.assignments}
        per_division: dict[str, int] = defaultdict(int)
        for a in self.assignments:
            per_division[str(a.division_id)] += 1
        total_people = summary.get("total_people", 0)
        summary.update(
            total_assignments=len(self.assignments),
            people_used=len(people_used),
            utilization_rate=(len(people_used) / total_people) if total_people else 0.0,
            understaffed_shift_count=sum(
                1 for w in warnings if w.severity is WarningSeverity.ERROR
            ),
            division_fallback_count=sum(1 for a in self.assignments if a.is_division_fallback),
            shifts_per_division=dict(per_division),
        )
        return summary


__all__ = ["Conflict", "EditError", "ScheduleEditor", "SlotKey"]
