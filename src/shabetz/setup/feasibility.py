"""Tells an administrator whether their configuration can actually be staffed.

An administrator who can configure anything can configure something impossible.
Without this, the only feedback is a generated schedule full of understaffing
warnings with no indication of which setting caused them.

The arithmetic that motivates it: three jobs needing 4x3, 2x3 and 1x1 people
demand 19 person-shifts a day, with per-window concurrency of 6/7/6.  Under an
eight-hour rest rule, whoever works 00:00-08:00 is free again at 16:00, so they
can take the evening window but never the middle one.  The crews for those two
windows must therefore be disjoint, putting the real floor at 6 + 7 = 13
distinct people -- not the 7 a naive peak-concurrency reading would suggest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import FeasibilityVerdict
from ..domain.models import EPS, HOURS_PER_DAY, Division, Job, Person, ShiftTemplate

TIGHT_MARGIN_RATIO = 0.2
"""Slack below this fraction of the floor is TIGHT: a roster with only a couple
of spare people loses coverage the moment anyone is unexpectedly absent."""


@dataclass(frozen=True, slots=True)
class WindowDemand:
    template_id: int
    template_name: str
    start_hour: float
    duration_hours: float
    concurrent_people: int


@dataclass(frozen=True, slots=True)
class SkillFloor:
    skill_id: int
    skill_name: str
    min_rank: int
    needed_distinct: int
    available: int

    @property
    def satisfied(self) -> bool:
        return self.available >= self.needed_distinct


@dataclass(frozen=True, slots=True)
class DivisionFeasibility:
    division_id: int
    division_name: str
    headcount: int
    expected_available: float
    minimum_distinct_needed: int
    verdict: FeasibilityVerdict
    messages: tuple[str, ...] = ()
    skill_floors: tuple[SkillFloor, ...] = ()


@dataclass(frozen=True, slots=True)
class FeasibilityReport:
    verdict: FeasibilityVerdict
    person_shifts_per_day: int
    minimum_distinct_needed: int
    peak_concurrent_people: int = 0
    window_demand: tuple[WindowDemand, ...] = ()
    divisions: tuple[DivisionFeasibility, ...] = ()
    messages: tuple[str, ...] = field(default_factory=tuple)


def _windows_are_mutually_exclusive(
    a: ShiftTemplate, b: ShiftTemplate, rest_hours: float
) -> bool:
    """Whether the rest rule forces disjoint crews for two windows on one day.

    Compared on a single day's timeline in both directions, since either window
    may be the earlier one.
    """
    for first, second in ((a, b), (b, a)):
        first_end = first.start_hour + first.duration_hours
        if second.start_hour + EPS >= first_end and (
            second.start_hour < first_end + rest_hours - EPS
        ):
            return True
    # Overlapping windows also demand separate people.
    a_end, b_end = a.start_hour + a.duration_hours, b.start_hour + b.duration_hours
    return a.start_hour < b_end - EPS and b.start_hour < a_end - EPS


def _peak_concurrency(
    templates: dict[int, ShiftTemplate], demand: dict[int, int]
) -> int:
    """Most people on duty at any one moment.

    Summed across templates rather than per template, because two separate
    windows covering the same hours both put people on the floor at once.
    Windows running past midnight wrap onto the same day's timeline, since every
    day of a steady schedule looks alike.
    """
    events: list[tuple[float, int]] = []
    for template_id, template in templates.items():
        count = demand[template_id]
        start = template.start_hour
        end = start + template.duration_hours
        segments = (
            [(start, min(end, HOURS_PER_DAY))]
            if end <= HOURS_PER_DAY
            else [(start, HOURS_PER_DAY), (0.0, min(end - HOURS_PER_DAY, HOURS_PER_DAY))]
        )
        for seg_start, seg_end in segments:
            if seg_end > seg_start:
                events.append((seg_start, count))
                events.append((seg_end, -count))

    if not events:
        return 0

    events.sort(key=lambda e: (e[0], e[1]))
    running = peak = 0
    for _, delta in events:
        running += delta
        peak = max(peak, running)
    return peak


def analyze(
    people: list[Person],
    jobs: list[Job],
    divisions: list[Division],
    rest_hours: float,
    rotation_enabled: bool,
) -> FeasibilityReport:
    templates: dict[int, ShiftTemplate] = {}
    demand_by_template: dict[int, int] = {}

    for job in jobs:
        for template in job.shift_templates:
            templates[template.id] = template
            demand_by_template[template.id] = (
                demand_by_template.get(template.id, 0) + job.required_people_per_shift
            )

    if not templates:
        return FeasibilityReport(
            verdict=FeasibilityVerdict.OK,
            person_shifts_per_day=0,
            minimum_distinct_needed=0,
            peak_concurrent_people=0,
            messages=("No jobs are configured with shift templates yet.",),
        )

    window_demand = tuple(
        WindowDemand(
            template_id=tid,
            template_name=templates[tid].name,
            start_hour=templates[tid].start_hour,
            duration_hours=templates[tid].duration_hours,
            concurrent_people=count,
        )
        for tid, count in sorted(
            demand_by_template.items(), key=lambda kv: templates[kv[0]].start_hour
        )
    )
    person_shifts = sum(demand_by_template.values())

    # Greedily group windows whose crews the rest rule allows to be shared; the
    # floor is the sum of the largest demand in each mutually-exclusive group.
    minimum_distinct = _minimum_distinct(templates, demand_by_template, rest_hours)

    division_reports = _per_division(
        people, jobs, divisions, minimum_distinct, rest_hours, rotation_enabled
    )

    if rotation_enabled and division_reports:
        worst = min(
            (d.verdict for d in division_reports),
            key=lambda v: (v is FeasibilityVerdict.OK, v is FeasibilityVerdict.TIGHT),
        )
        overall = worst
    else:
        total_expected = sum(_expected_available(people, None) for _ in [0])
        overall = _verdict_for(total_expected, minimum_distinct)

    messages: list[str] = []
    if overall is FeasibilityVerdict.INFEASIBLE:
        messages.append(
            f"Configuration needs at least {minimum_distinct} distinct people per day "
            f"({person_shifts} person-shifts). Add people, reduce head count, "
            f"shorten the rest window, or relax the rotation policy."
        )
    elif overall is FeasibilityVerdict.TIGHT:
        messages.append(
            f"Configuration needs {minimum_distinct} distinct people per day and has "
            f"little slack; absence will cause understaffing."
        )

    return FeasibilityReport(
        verdict=overall,
        person_shifts_per_day=person_shifts,
        minimum_distinct_needed=minimum_distinct,
        peak_concurrent_people=_peak_concurrency(templates, demand_by_template),
        window_demand=window_demand,
        divisions=tuple(division_reports),
        messages=tuple(messages),
    )


def _minimum_distinct(
    templates: dict[int, ShiftTemplate],
    demand: dict[int, int],
    rest_hours: float,
) -> int:
    """Floor on distinct people per day, honouring rest-enforced disjointness."""
    remaining = sorted(templates.values(), key=lambda t: t.start_hour)
    groups: list[list[ShiftTemplate]] = []

    for template in remaining:
        placed = False
        for group in groups:
            # A window may share a group only if it can share crews with every
            # window already in it.
            if all(
                not _windows_are_mutually_exclusive(template, other, rest_hours)
                for other in group
            ):
                group.append(template)
                placed = True
                break
        if not placed:
            groups.append([template])

    return sum(max(demand[t.id] for t in group) for group in groups)


def _expected_available(people: list[Person], division_id: int | None) -> float:
    """Expected people available on an arbitrary day, from working-day patterns."""
    pool = [p for p in people if division_id is None or p.division_id == division_id]
    if not pool:
        return 0.0
    return sum(len(p.working_weekdays) / 7.0 for p in pool)


def _verdict_for(expected_available: float, needed: int) -> FeasibilityVerdict:
    if needed == 0:
        return FeasibilityVerdict.OK
    if expected_available < needed:
        return FeasibilityVerdict.INFEASIBLE
    if expected_available - needed < needed * TIGHT_MARGIN_RATIO:
        return FeasibilityVerdict.TIGHT
    return FeasibilityVerdict.OK


def _per_division(
    people: list[Person],
    jobs: list[Job],
    divisions: list[Division],
    minimum_distinct: int,
    rest_hours: float,
    rotation_enabled: bool,
) -> list[DivisionFeasibility]:
    reports: list[DivisionFeasibility] = []

    for division in divisions:
        members = [p for p in people if p.division_id == division.id]
        expected = _expected_available(people, division.id)
        # Without rotation the whole roster covers every day, so a single
        # division is never expected to carry the full load alone.
        needed = minimum_distinct if rotation_enabled else 0
        verdict = _verdict_for(expected, needed)

        messages: list[str] = []
        if rotation_enabled and verdict is FeasibilityVerdict.INFEASIBLE:
            messages.append(
                f"{division.name} has {len(members)} people (about {expected:.1f} "
                f"available on a given day) but duty days need {needed} distinct people."
            )

        floors = _skill_floors(members, jobs, rest_hours)
        for floor in floors:
            if not floor.satisfied:
                messages.append(
                    f"{division.name} needs at least {floor.needed_distinct} people at "
                    f"{floor.skill_name} (rank {floor.min_rank}+) but has {floor.available}."
                )
                if verdict is FeasibilityVerdict.OK:
                    verdict = FeasibilityVerdict.INFEASIBLE

        reports.append(
            DivisionFeasibility(
                division_id=division.id,
                division_name=division.name,
                headcount=len(members),
                expected_available=round(expected, 2),
                minimum_distinct_needed=needed,
                verdict=verdict,
                messages=tuple(messages),
                skill_floors=floors,
            )
        )

    return reports


def _skill_floors(
    members: list[Person], jobs: list[Job], rest_hours: float
) -> tuple[SkillFloor, ...]:
    """How many distinct holders of each named-role skill a duty day needs."""
    needs: dict[tuple[int, int], tuple[str, int]] = {}

    for job in jobs:
        for requirement in job.role_requirements:
            key = (requirement.skill_id, requirement.min_rank)
            per_window = requirement.required_count or 0
            group_count = _minimum_distinct(
                {t.id: t for t in job.shift_templates},
                {t.id: per_window for t in job.shift_templates},
                rest_hours,
            )
            name, existing = needs.get(key, (requirement.skill_name, 0))
            needs[key] = (name, existing + group_count)

    floors = []
    for (skill_id, min_rank), (name, needed) in sorted(needs.items()):
        available = sum(
            1 for p in members if p.skill_ranks.get(skill_id, -1) >= min_rank
        )
        floors.append(
            SkillFloor(
                skill_id=skill_id,
                skill_name=name,
                min_rank=min_rank,
                needed_distinct=needed,
                available=available,
            )
        )
    return tuple(floors)
