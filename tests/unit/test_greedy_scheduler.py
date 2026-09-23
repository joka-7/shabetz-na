"""The six behaviours the engine must preserve, plus structural guarantees."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from shabetz.domain.enums import AssignmentRole, WarningKind, WarningSeverity
from shabetz.domain.models import EPS, TimeOffPeriod
from shabetz.domain.state import SchedulerState
from shabetz.scheduling.greedy import SimpleGreedyScheduler
from tests.factories import (
    job,
    params,
    person,
    requirement,
    roster,
    template,
    three_eight_hour_blocks,
)

D1 = date(2026, 10, 1)


# --------------------------------------------------------------- requirement 1


@pytest.mark.timeout(5)
def test_date_iteration_terminates_and_covers_range() -> None:
    result = SimpleGreedyScheduler().generate(
        roster(6),
        [job(1, "Coverage", 2, three_eight_hour_blocks())],
        params(D1, D1 + timedelta(days=13)),
    )
    dates = {a.calendar_date for a in result.assignments}
    assert len(dates) == 14
    assert min(dates) == D1
    assert max(dates) == D1 + timedelta(days=13)


@pytest.mark.timeout(5)
def test_single_day_range_produces_one_day() -> None:
    result = SimpleGreedyScheduler().generate(
        roster(6), [job(1, "Coverage", 2, three_eight_hour_blocks())], params(D1, D1)
    )
    assert {a.calendar_date for a in result.assignments} == {D1}


# --------------------------------------------------------------- requirement 2


def test_shift_slots_derived_from_templates() -> None:
    scheduler = SimpleGreedyScheduler()

    three = scheduler.generate(
        roster(9), [job(1, "Round the clock", 1, three_eight_hour_blocks())], params(D1, D1)
    )
    assert len({a.template_id for a in three.assignments}) == 3

    one = scheduler.generate(
        roster(9),
        [job(1, "Day only", 1, (template(9, "Day", 8.0),))],
        params(D1, D1),
    )
    assert len(one.assignments) == 1


def test_template_start_hour_places_shift_where_configured() -> None:
    result = SimpleGreedyScheduler().generate(
        roster(2), [job(1, "Day", 1, (template(9, "Day", 8.0),))], params(D1, D1)
    )
    assert result.assignments[0].start_abs == 8.0
    assert result.assignments[0].end_abs == 16.0


def test_template_crossing_midnight() -> None:
    """Arbitrary start hours make overnight windows genuinely reachable."""
    night = template(9, "Night", 22.0)
    result = SimpleGreedyScheduler().generate(
        roster(2), [job(1, "Night watch", 1, (night,))], params(D1, D1)
    )
    assignment = result.assignments[0]
    assert assignment.start_abs == 22.0
    assert assignment.end_abs == 30.0

    from shabetz.domain.models import ShiftSlot

    slot = ShiftSlot.build(job(1, "Night watch", 1, (night,)), night, D1, 0)
    assert slot.clock_start == 22.0
    assert slot.clock_end == 6.0
    assert slot.crosses_midnight is True
    assert slot.end_calendar_date == D1 + timedelta(days=1)


def test_window_ending_at_midnight_does_not_cross() -> None:
    from shabetz.domain.models import ShiftSlot

    evening = template(3, "Evening", 16.0)
    slot = ShiftSlot.build(job(1, "J", 1, (evening,)), evening, D1, 0)
    assert slot.crosses_midnight is False
    assert slot.end_calendar_date == D1


# --------------------------------------------------------------- requirement 3


def test_job_sort_key_ordering() -> None:
    """Named directly so a regression reports itself instead of a shortfall."""
    scarce = job(10, "Scarce", 1, (template(9, "Day", 8.0),), (requirement(1, 100, 3, count=1),))
    broad = job(20, "Broad", 4, three_eight_hour_blocks())
    other = job(30, "Other", 2, three_eight_hour_blocks())
    assert [j.id for j in sorted([broad, other, scarce], key=lambda j: j.sort_key)] == [
        10,
        20,
        30,
    ]


def test_scarce_job_staffed_before_general_pool() -> None:
    """The only qualified specialists also qualify for the broad job."""
    specialists = [person(i, skills={100: 3, 200: 1}) for i in (1, 2)]
    generalists = [person(i, skills={200: 1}) for i in range(3, 12)]

    scarce = job(
        10,
        "Specialist duty",
        1,
        (template(9, "Day", 8.0),),
        (requirement(1, 100, 3, name="Specialism", count=1),),
    )
    broad = job(20, "General work", 4, three_eight_hour_blocks(), (requirement(2, 200, 1),))

    result = SimpleGreedyScheduler().generate(
        specialists + generalists, [broad, scarce], params(D1, D1 + timedelta(days=6))
    )

    staffed_days = {a.calendar_date for a in result.assignments if a.job_id == 10}
    assert len(staffed_days) == 7, "scarce job must be staffed every day"


# --------------------------------------------------------------- requirement 4


def test_mandatory_role_assigned_before_general_fill() -> None:
    """A single-pass greedy would burn the only lead as general fill."""
    lead = person(1, skills={100: 3, 200: 1}, name="The Lead")
    others = [person(i, skills={200: 1}) for i in range(2, 9)]

    work = job(
        1,
        "Led work",
        4,
        (template(9, "Day", 8.0),),
        (
            requirement(1, 100, 3, name="Leadership", count=1, leadership=True),
            requirement(2, 200, 1, name="Baseline"),
        ),
    )

    result = SimpleGreedyScheduler().generate([lead, *others], [work], params(D1, D1))

    assert len(result.assignments) == 4
    roles = [a for a in result.assignments if a.role is AssignmentRole.ROLE]
    assert len(roles) == 1
    assert roles[0].person_id == lead.id
    assert not [w for w in result.warnings if w.kind is WarningKind.MISSING_ROLE]


def test_multiple_distinct_role_requirements() -> None:
    """The generalized model supports more than one named role per shift."""
    lead = person(1, skills={100: 3, 300: 1})
    medic = person(2, skills={200: 2, 300: 1})
    fill = [person(i, skills={300: 1}) for i in range(3, 8)]

    work = job(
        1,
        "Crew",
        4,
        (template(9, "Day", 8.0),),
        (
            requirement(1, 100, 3, name="Lead", count=1),
            requirement(2, 200, 2, name="Medic", count=1),
            requirement(3, 300, 1, name="Baseline"),
        ),
    )

    result = SimpleGreedyScheduler().generate([lead, medic, *fill], [work], params(D1, D1))

    satisfied = {a.satisfied_requirement_id for a in result.assignments}
    assert {1, 2} <= satisfied
    assert len(result.assignments) == 4
    assert not [w for w in result.warnings if w.kind is WarningKind.MISSING_ROLE]


def test_role_only_job_fills_exactly_once() -> None:
    """Head count 1 entirely satisfied by the role: no double-booking, no over-fill."""
    manager = person(1, skills={100: 4})
    work = job(
        1,
        "Single seat",
        1,
        (template(9, "Day", 8.0),),
        (requirement(1, 100, 4, name="Manager", count=1),),
    )
    result = SimpleGreedyScheduler().generate([manager, person(2)], [work], params(D1, D1))

    assert len(result.assignments) == 1
    assert result.assignments[0].person_id == manager.id
    assert result.assignments[0].role is AssignmentRole.ROLE


# --------------------------------------------------------------- requirement 5


def test_cold_start_allows_first_slot_at_hour_zero() -> None:
    result = SimpleGreedyScheduler().generate(
        [person(1)], [job(1, "Midnight", 1, (template(1, "Block A", 0.0),))], params(D1, D1)
    )
    assert len(result.assignments) == 1
    assert result.assignments[0].start_abs == 0.0


def test_initial_availability_is_negative_rest() -> None:
    """Pinned so the offset cannot be tidied back to zero."""
    state = SchedulerState([person(1)], rest_period_hours=8.0)
    assert state.snapshot()[1].available_from_hours == -8.0


# --------------------------------------------------------------- requirement 6


def test_understaffing_is_reported_not_swallowed() -> None:
    result = SimpleGreedyScheduler().generate(
        [person(1)], [job(1, "Needs four", 4, (template(9, "Day", 8.0),))], params(D1, D1)
    )

    assert len(result.assignments) == 1
    understaffed = [w for w in result.warnings if w.kind is WarningKind.UNDERSTAFFED]
    assert len(understaffed) == 1
    warning = understaffed[0]
    assert warning.severity is WarningSeverity.ERROR
    assert warning.required == 4
    assert warning.assigned == 1
    assert warning.calendar_date == D1
    assert warning.job_id == 1
    # Carried separately so a client can word the warning in its own language.
    assert (warning.job_name, warning.template_name) == ("Needs four", "Day")
    assert result.summary.understaffed_shift_count == 1


def test_missing_role_is_reported() -> None:
    result = SimpleGreedyScheduler().generate(
        roster(4),
        [
            job(
                1,
                "Led work",
                2,
                (template(9, "Day", 8.0),),
                (requirement(1, 100, 3, name="Leadership", count=1),),
            )
        ],
        params(D1, D1),
    )
    missing = [w for w in result.warnings if w.kind is WarningKind.MISSING_ROLE]
    assert missing
    assert missing[0].skill_name == "Leadership"


# ------------------------------------------------------- structural guarantees


def test_no_rest_violation_in_full_schedule() -> None:
    """Validates the entire engine output in one sweep.

    With no cap on shifts per day, the rest window is the only structural limit
    on a person's workload, which makes this the most important assertion here.
    """
    rest = 8.0
    result = SimpleGreedyScheduler().generate(
        roster(20, skills={1: 2}),
        [
            job(1, "Round the clock", 4, three_eight_hour_blocks(), (requirement(1, 1, 1),)),
            job(2, "Day desk", 1, (template(9, "Day", 8.0),)),
        ],
        params(D1, D1 + timedelta(days=13), rest=rest),
    )

    by_person: dict[int, list[tuple[float, float]]] = {}
    for a in result.assignments:
        by_person.setdefault(a.person_id, []).append((a.start_abs, a.end_abs))

    for person_id, windows in by_person.items():
        windows.sort()
        for (_, prev_end), (next_start, _) in zip(windows, windows[1:], strict=False):
            assert next_start >= prev_end + rest - EPS, (
                f"person {person_id} violates the rest window"
            )


@pytest.mark.parametrize(
    ("gap", "allowed"),
    [(8.0, True), (7.999, False), (8.001, True)],
)
def test_rest_boundary_inclusive(gap: float, allowed: bool) -> None:
    """Pins the boundary as inclusive: exactly one rest window apart is legal."""
    first = template(1, "First", 0.0, duration=8.0)
    second = template(2, "Second", 8.0 + gap, duration=1.0)
    result = SimpleGreedyScheduler().generate(
        [person(1)],
        [job(1, "Back to back", 1, (first, second))],
        params(D1, D1, rest=8.0),
    )
    assert (len(result.assignments) == 2) is allowed


def test_short_rest_permits_many_shifts_per_day() -> None:
    """There is no shifts-per-day cap; rest alone governs."""
    templates = tuple(template(i + 1, f"T{i}", i * 4.0, duration=4.0) for i in range(6))
    result = SimpleGreedyScheduler().generate(
        [person(1)], [job(1, "Dense", 1, templates)], params(D1, D1, rest=0.0)
    )
    assert len(result.assignments) == 6


def test_overlapping_templates_prevent_double_booking() -> None:
    overlapping = (template(1, "Early", 8.0, duration=8.0), template(2, "Mid", 12.0, duration=8.0))
    result = SimpleGreedyScheduler().generate(
        roster(4), [job(1, "Overlap", 1, overlapping)], params(D1, D1, rest=0.0)
    )
    assert len({a.person_id for a in result.assignments}) == 2


def test_schedule_is_deterministic() -> None:
    def run() -> list[tuple[int, int, float]]:
        result = SimpleGreedyScheduler().generate(
            roster(12),
            [job(1, "A", 3, three_eight_hour_blocks()), job(2, "B", 2, three_eight_hour_blocks())],
            params(D1, D1 + timedelta(days=6)),
        )
        return [(a.person_id, a.job_id, a.start_abs) for a in result.assignments]

    assert run() == run()


def test_time_off_and_non_working_days_excluded() -> None:
    away = person(1, time_off=(TimeOffPeriod(D1, D1 + timedelta(days=2)),))
    weekender = person(2, weekdays=frozenset({5, 6}))
    result = SimpleGreedyScheduler().generate(
        [away, weekender],
        [job(1, "Desk", 2, (template(9, "Day", 8.0),))],
        params(D1, D1 + timedelta(days=2)),
    )
    assert away.id not in {a.person_id for a in result.assignments}
    for assignment in result.assignments:
        assert assignment.calendar_date.weekday() in (5, 6)


def test_configurable_levels_compare_by_rank() -> None:
    """A six-rung ladder with unusual names still resolves 'at least X'."""
    novice, adept = 0, 4
    low = person(1, skills={7: novice})
    high = person(2, skills={7: adept})
    result = SimpleGreedyScheduler().generate(
        [low, high],
        [
            job(
                1,
                "Skilled",
                1,
                (template(9, "Day", 8.0),),
                (requirement(1, 7, adept, name="Adept", count=1),),
            )
        ],
        params(D1, D1),
    )
    assert [a.person_id for a in result.assignments] == [high.id]
