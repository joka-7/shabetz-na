"""A greedy scheduler driven entirely by configuration.

The algorithm preserves six behaviours the original engine had to be fixed into,
each pinned by a named test in ``tests/unit/test_greedy_scheduler.py``:

1. Date iteration terminates and covers the requested range.
2. Shift slots are derived from the job's configured templates.
3. Jobs are ordered so scarce, highly-skilled work is staffed before general
   pools exhaust the roster.
4. Named role requirements are satisfied before general head count is filled.
5. Availability is seeded behind the horizon so hour-zero shifts are reachable.
6. Understaffing is reported rather than silently swallowed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta

from ..domain.enums import (
    AssignmentRole,
    DivisionPolicy,
    WarningKind,
    WarningSeverity,
)
from ..domain.models import (
    Assignment,
    Job,
    Person,
    ScheduleParams,
    ScheduleWarning,
    ShiftSlot,
    SkillRequirement,
)
from ..domain.state import SchedulerState
from .result import ScheduleResult, build_summary
from .rotation import DivisionRotation
from .strategy import SchedulingStrategy


class SimpleGreedyScheduler(SchedulingStrategy):
    def generate(
        self,
        people: Sequence[Person],
        jobs: Sequence[Job],
        params: ScheduleParams,
    ) -> ScheduleResult:
        state = SchedulerState(people, params.rest_period_hours)
        rotation = DivisionRotation(
            division_order=params.division_order,
            block_days=params.rotation_block_days,
            anchor=params.anchor,
            enabled=params.rotation_enabled,
        )

        by_division: dict[int, list[Person]] = defaultdict(list)
        for person in people:
            by_division[person.division_id].append(person)

        # Starvation prevention: low-frequency and highly-constrained jobs are
        # staffed before broad 24/7 pools drain the roster.
        ordered_jobs = sorted(jobs, key=lambda job: job.sort_key)

        assignments: list[Assignment] = []
        warnings: list[ScheduleWarning] = []
        active_by_day: dict[date, int | None] = {}

        day = params.start_date
        day_index = 0
        while day <= params.end_date:
            active = rotation.active_division(day)
            active_by_day[day] = active

            for job in ordered_jobs:
                for template in job.shift_templates:
                    slot = ShiftSlot.build(job, template, day, day_index)
                    picked = self._staff_slot(job, slot, by_division, rotation, active, state, day)
                    assignments.extend(picked)
                    self._record_shortfalls(job, slot, picked, warnings)

            # Advancing with an explicit timedelta is what keeps this loop
            # finite; the original spun forever without it.
            day += timedelta(days=1)
            day_index += 1

        assignment_tuple = tuple(assignments)
        warning_tuple = tuple(warnings)
        return ScheduleResult(
            assignments=assignment_tuple,
            warnings=warning_tuple,
            summary=build_summary(
                assignment_tuple, warning_tuple, tuple(people), params, active_by_day
            ),
        )

    # ------------------------------------------------------------------ slots

    def _staff_slot(
        self,
        job: Job,
        slot: ShiftSlot,
        by_division: dict[int, list[Person]],
        rotation: DivisionRotation,
        active: int | None,
        state: SchedulerState,
        day: date,
    ) -> list[Assignment]:
        tiers = self._candidate_tiers(job, by_division, rotation, active, day)
        chosen: list[Assignment] = []
        taken: set[int] = set()

        # Phase 1 - satisfy every requirement that names a specific number of
        # people.  Ordered by scarcity so the hardest role is filled while the
        # widest choice remains.  A single-pass greedy would spend the only
        # qualified person as general fill and leave the role unfilled.
        for requirement in self._role_requirements_by_scarcity(job, tiers):
            still_needed = requirement.required_count or 0
            already = sum(
                1 for assignment in chosen if assignment.satisfied_requirement_id == requirement.id
            )
            for _ in range(max(0, still_needed - already)):
                if len(chosen) >= job.required_people_per_shift:
                    break
                needed = (*job.blanket_requirements, requirement)
                picked = self._pick(tiers, state, slot, needed, taken)
                if picked is None:
                    break
                person, tier_index = picked
                state.commit(person, slot)
                taken.add(person.id)
                chosen.append(
                    self._assignment(
                        person, job, slot, AssignmentRole.ROLE, tier_index > 0, requirement.id
                    )
                )

        # Phase 2 - fill the remaining head count with anyone meeting the
        # requirements that apply to every member.
        while len(chosen) < job.required_people_per_shift:
            picked = self._pick(tiers, state, slot, job.blanket_requirements, taken)
            if picked is None:
                break
            person, tier_index = picked
            state.commit(person, slot)
            taken.add(person.id)
            chosen.append(
                self._assignment(person, job, slot, AssignmentRole.MEMBER, tier_index > 0, None)
            )

        return chosen

    def _candidate_tiers(
        self,
        job: Job,
        by_division: dict[int, list[Person]],
        rotation: DivisionRotation,
        active: int | None,
        day: date,
    ) -> list[list[Person]]:
        """Ordered pools to draw from, most preferred first."""
        everyone = [p for people in by_division.values() for p in people]

        if job.division_policy is DivisionPolicy.ANY_DIVISION or active is None:
            return [everyone]

        active_pool = list(by_division.get(active, []))
        if job.division_policy is DivisionPolicy.ACTIVE_DIVISION_ONLY:
            return [active_pool]

        # Preferred: the active division first, then the rest ordered by how
        # soon each takes duty, so we borrow from whoever is on deck next.
        others = sorted(
            (div for div in by_division if div != active),
            key=lambda div: rotation.distance_from_active(div, day),
        )
        return [active_pool, *[list(by_division[div]) for div in others]]

    def _role_requirements_by_scarcity(
        self, job: Job, tiers: list[list[Person]]
    ) -> list[SkillRequirement]:
        """Hardest-to-fill role requirements first."""
        candidates = [person for tier in tiers for person in tier]

        def qualified_count(requirement: SkillRequirement) -> int:
            return sum(1 for person in candidates if person.meets(requirement))

        return sorted(
            job.role_requirements,
            key=lambda r: (qualified_count(r), -r.min_rank, r.id),
        )

    def _pick(
        self,
        tiers: list[list[Person]],
        state: SchedulerState,
        slot: ShiftSlot,
        requirements: Sequence[SkillRequirement],
        taken: set[int],
    ) -> tuple[Person, int] | None:
        for tier_index, tier in enumerate(tiers):
            eligible = [
                person
                for person in tier
                if person.id not in taken
                and person.meets_all(requirements)
                and state.can_work(person, slot)
            ]
            if eligible:
                # Fairness first, then longest idle; the id tie-break is what
                # makes a run byte-reproducible.
                eligible.sort(key=lambda p: (*state.load(p.id), p.id))
                return eligible[0], tier_index
        return None

    # --------------------------------------------------------------- warnings

    def _record_shortfalls(
        self,
        job: Job,
        slot: ShiftSlot,
        picked: list[Assignment],
        warnings: list[ScheduleWarning],
    ) -> None:
        if len(picked) < job.required_people_per_shift:
            warnings.append(
                ScheduleWarning(
                    kind=WarningKind.UNDERSTAFFED,
                    severity=WarningSeverity.ERROR,
                    message=(
                        f"{job.name} on {slot.calendar_date.isoformat()} "
                        f"({slot.template_name}) has {len(picked)} of "
                        f"{job.required_people_per_shift} required staff"
                    ),
                    calendar_date=slot.calendar_date,
                    job_id=job.id,
                    template_id=slot.template_id,
                    required=job.required_people_per_shift,
                    assigned=len(picked),
                )
            )

        for requirement in job.role_requirements:
            filled = sum(1 for a in picked if a.satisfied_requirement_id == requirement.id)
            if filled < (requirement.required_count or 0):
                warnings.append(
                    ScheduleWarning(
                        kind=WarningKind.MISSING_ROLE,
                        severity=WarningSeverity.ERROR,
                        message=(
                            f"{job.name} on {slot.calendar_date.isoformat()} "
                            f"({slot.template_name}) needs "
                            f"{requirement.required_count} x {requirement.skill_name} "
                            f"but filled {filled}"
                        ),
                        calendar_date=slot.calendar_date,
                        job_id=job.id,
                        template_id=slot.template_id,
                        required=requirement.required_count,
                        assigned=filled,
                    )
                )

        for assignment in picked:
            if assignment.is_division_fallback:
                warnings.append(
                    ScheduleWarning(
                        kind=WarningKind.DIVISION_FALLBACK,
                        severity=WarningSeverity.INFO,
                        message=(
                            f"{assignment.person_name} was borrowed from outside the "
                            f"active division for {job.name} on "
                            f"{slot.calendar_date.isoformat()}"
                        ),
                        calendar_date=slot.calendar_date,
                        job_id=job.id,
                        template_id=slot.template_id,
                    )
                )

    @staticmethod
    def _assignment(
        person: Person,
        job: Job,
        slot: ShiftSlot,
        role: AssignmentRole,
        is_fallback: bool,
        requirement_id: int | None,
    ) -> Assignment:
        return Assignment(
            person_id=person.id,
            person_name=person.full_name,
            division_id=person.division_id,
            job_id=job.id,
            job_name=job.name,
            template_id=slot.template_id,
            template_name=slot.template_name,
            calendar_date=slot.calendar_date,
            start_abs=slot.start_abs,
            end_abs=slot.end_abs,
            role=role,
            is_division_fallback=is_fallback,
            satisfied_requirement_id=requirement_id,
        )
