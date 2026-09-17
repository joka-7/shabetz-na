"""Rotation cadence, wraparound, anchoring, and the division policies."""

from __future__ import annotations

from datetime import date, timedelta

from shabetz.domain.enums import DivisionPolicy
from shabetz.scheduling.greedy import SimpleGreedyScheduler
from shabetz.scheduling.rotation import DivisionRotation
from tests.factories import job, params, person, template, three_eight_hour_blocks

D1 = date(2026, 10, 1)
ORDER = (11, 22, 33, 44)


def test_rotation_cadence_and_wraparound() -> None:
    rotation = DivisionRotation(ORDER, block_days=2, anchor=D1)
    actual = [rotation.active_division(D1 + timedelta(days=i)) for i in range(10)]
    assert actual == [11, 11, 22, 22, 33, 33, 44, 44, 11, 11]


def test_rotation_block_length_is_configurable() -> None:
    rotation = DivisionRotation(ORDER, block_days=3, anchor=D1)
    assert [rotation.active_division(D1 + timedelta(days=i)) for i in range(6)] == [
        11, 11, 11, 22, 22, 22,
    ]


def test_rotation_supports_any_number_of_divisions() -> None:
    rotation = DivisionRotation((5, 6, 7, 8, 9, 10, 11), block_days=1, anchor=D1)
    assert [rotation.active_division(D1 + timedelta(days=i)) for i in range(8)] == [
        5, 6, 7, 8, 9, 10, 11, 5,
    ]


def test_rotation_anchor_is_stable_across_windows() -> None:
    """Regenerating a later window must not shift who holds duty."""
    rotation = DivisionRotation(ORDER, block_days=2, anchor=D1)
    later = D1 + timedelta(days=30)
    same = DivisionRotation(ORDER, block_days=2, anchor=D1)
    assert rotation.active_division(later) == same.active_division(later)


def test_rotation_disabled_uses_full_roster() -> None:
    people = [person(1, division_id=11), person(2, division_id=22)]
    result = SimpleGreedyScheduler().generate(
        people,
        [job(1, "Work", 2, (template(9, "Day", 8.0),), policy=DivisionPolicy.ACTIVE_DIVISION_ONLY)],
        params(D1, D1, rotation=False, divisions=ORDER),
    )
    assert len(result.assignments) == 2


def test_division_policy_only_never_borrows() -> None:
    people = [person(1, division_id=11), *[person(i, division_id=22) for i in range(2, 9)]]
    result = SimpleGreedyScheduler().generate(
        people,
        [job(1, "Duty", 4, (template(9, "Day", 8.0),), policy=DivisionPolicy.ACTIVE_DIVISION_ONLY)],
        params(D1, D1, rotation=True, divisions=ORDER, anchor=D1),
    )
    assert {a.division_id for a in result.assignments} == {11}
    assert result.summary.understaffed_shift_count == 1


def test_division_policy_preferred_borrows_and_flags() -> None:
    people = [person(1, division_id=11), *[person(i, division_id=22) for i in range(2, 9)]]
    result = SimpleGreedyScheduler().generate(
        people,
        [
            job(
                1,
                "Duty",
                4,
                (template(9, "Day", 8.0),),
                policy=DivisionPolicy.ACTIVE_DIVISION_PREFERRED,
            )
        ],
        params(D1, D1, rotation=True, divisions=ORDER, anchor=D1),
    )
    assert len(result.assignments) == 4
    assert result.summary.understaffed_shift_count == 0
    borrowed = [a for a in result.assignments if a.is_division_fallback]
    assert len(borrowed) == 3
    assert all(a.division_id == 22 for a in borrowed)


def test_division_policy_preferred_drains_active_division_first() -> None:
    active = [person(i, division_id=11) for i in range(1, 5)]
    other = [person(i, division_id=22) for i in range(5, 9)]
    result = SimpleGreedyScheduler().generate(
        active + other,
        [job(1, "Duty", 4, (template(9, "Day", 8.0),))],
        params(D1, D1, rotation=True, divisions=ORDER, anchor=D1),
    )
    assert {a.division_id for a in result.assignments} == {11}
    assert not [a for a in result.assignments if a.is_division_fallback]


def test_division_policy_any_draws_flat() -> None:
    people = [person(1, division_id=11), *[person(i, division_id=22) for i in range(2, 9)]]
    result = SimpleGreedyScheduler().generate(
        people,
        [job(1, "Open", 4, (template(9, "Day", 8.0),), policy=DivisionPolicy.ANY_DIVISION)],
        params(D1, D1, rotation=True, divisions=ORDER, anchor=D1),
    )
    assert len(result.assignments) == 4
    assert not [a for a in result.assignments if a.is_division_fallback]


def test_rotation_summary_records_active_division_per_day() -> None:
    result = SimpleGreedyScheduler().generate(
        [person(1, division_id=11)],
        [job(1, "Work", 1, three_eight_hour_blocks())],
        params(D1, D1 + timedelta(days=3), rotation=True, divisions=ORDER, anchor=D1),
    )
    assert list(result.summary.active_division_by_day.values()) == [11, 11, 22, 22]
