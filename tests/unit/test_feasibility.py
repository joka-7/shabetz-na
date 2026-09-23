"""Feasibility preflight: does it catch configurations that cannot be staffed?"""

from __future__ import annotations

from shabetz.domain.enums import FeasibilityVerdict
from shabetz.domain.models import Division
from shabetz.setup.feasibility import analyze
from tests.factories import job, person, requirement, template, three_eight_hour_blocks

ALL_WEEK = frozenset(range(7))
FIVE_DAYS = frozenset(range(5))


def _divisions(*ids: int) -> list[Division]:
    return [Division(id=i, name=f"Division {i}", display_order=n) for n, i in enumerate(ids)]


def _example_jobs() -> list:
    blocks = three_eight_hour_blocks()
    day_only = (template(4, "Day", 8.0),)
    return [
        job(1, "Broad coverage", 4, blocks),
        job(2, "Specialist coverage", 2, blocks),
        job(3, "Single day desk", 1, day_only),
    ]


def test_minimum_distinct_exceeds_peak_concurrency() -> None:
    """The rest rule forces disjoint crews, so the floor is 13, not the peak 7."""
    report = analyze(
        people=[person(i, division_id=1, weekdays=ALL_WEEK) for i in range(1, 16)],
        jobs=_example_jobs(),
        divisions=_divisions(1),
        rest_hours=8.0,
        rotation_enabled=True,
    )

    assert report.person_shifts_per_day == 19
    # Two templates both cover 08:00-16:00, so the busiest moment carries 7
    # people even though no single window demands more than 6.
    assert max(w.concurrent_people for w in report.window_demand) == 6
    assert report.peak_concurrent_people == 7
    # The floor is nearly double the peak: morning and midday crews cannot be
    # the same people, so their head counts add rather than overlap.
    assert report.minimum_distinct_needed == 13


def test_full_week_roster_of_fifteen_is_tight_not_comfortable() -> None:
    report = analyze(
        people=[person(i, division_id=1, weekdays=ALL_WEEK) for i in range(1, 16)],
        jobs=_example_jobs(),
        divisions=_divisions(1),
        rest_hours=8.0,
        rotation_enabled=True,
    )
    assert report.verdict is FeasibilityVerdict.TIGHT


def test_five_day_week_falls_below_the_floor() -> None:
    """15 people at a 5-day week average ~10.7 available, under the 13 floor."""
    report = analyze(
        people=[person(i, division_id=1, weekdays=FIVE_DAYS) for i in range(1, 16)],
        jobs=_example_jobs(),
        divisions=_divisions(1),
        rest_hours=8.0,
        rotation_enabled=True,
    )
    assert report.verdict is FeasibilityVerdict.INFEASIBLE
    assert report.divisions[0].expected_available < 13
    assert report.messages


def test_adding_people_flips_infeasible_to_ok() -> None:
    jobs = _example_jobs()
    divisions = _divisions(1)

    short = analyze(
        [person(i, division_id=1, weekdays=FIVE_DAYS) for i in range(1, 16)],
        jobs,
        divisions,
        8.0,
        True,
    )
    assert short.verdict is FeasibilityVerdict.INFEASIBLE

    plenty = analyze(
        [person(i, division_id=1, weekdays=FIVE_DAYS) for i in range(1, 40)],
        jobs,
        divisions,
        8.0,
        True,
    )
    assert plenty.verdict is FeasibilityVerdict.OK


def test_shorter_rest_lowers_the_floor() -> None:
    """With no rest window, crews may be shared and only the peak binds."""
    people = [person(i, division_id=1, weekdays=ALL_WEEK) for i in range(1, 16)]
    relaxed = analyze(people, _example_jobs(), _divisions(1), 0.0, True)
    assert relaxed.minimum_distinct_needed == relaxed.peak_concurrent_people == 7


def test_missing_skill_holders_reported_per_division() -> None:
    blocks = three_eight_hour_blocks()
    led = job(
        1,
        "Led work",
        2,
        blocks,
        (requirement(1, 100, 3, name="Team Leader", count=1),),
    )
    # Nobody holds the leadership skill at all.
    people = [person(i, division_id=1, weekdays=ALL_WEEK) for i in range(1, 30)]
    report = analyze(people, [led], _divisions(1), 8.0, True)

    assert report.divisions[0].verdict is FeasibilityVerdict.INFEASIBLE
    floor = report.divisions[0].skill_floors[0]
    assert floor.skill_name == "Team Leader"
    assert floor.available == 0
    assert floor.needed_distinct == 2
    assert any("Team Leader" in m for m in report.divisions[0].messages)


def test_leadership_floor_accounts_for_disjoint_windows() -> None:
    """Two of three 8h windows need separate leads, so the floor is 2 not 1."""
    blocks = three_eight_hour_blocks()
    led = job(1, "Led", 2, blocks, (requirement(1, 100, 3, name="Lead", count=1),))
    people = [person(i, division_id=1, weekdays=ALL_WEEK, skills={100: 3}) for i in range(1, 4)]
    report = analyze(people, [led], _divisions(1), 8.0, True)
    assert report.divisions[0].skill_floors[0].needed_distinct == 2


def test_no_jobs_is_trivially_ok() -> None:
    report = analyze([], [], _divisions(1), 8.0, True)
    assert report.verdict is FeasibilityVerdict.OK
    assert report.minimum_distinct_needed == 0


def test_rotation_disabled_does_not_demand_per_division_coverage() -> None:
    """Without rotation the whole roster covers every day."""
    people = [person(i, division_id=(i % 4) + 1, weekdays=ALL_WEEK) for i in range(1, 61)]
    report = analyze(people, _example_jobs(), _divisions(1, 2, 3, 4), 8.0, False)
    assert report.verdict is FeasibilityVerdict.OK
