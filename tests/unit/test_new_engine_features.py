"""Lapsing skills, fairness carried across schedules, and the calendar feed format."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from shabetz.scheduling.greedy import SimpleGreedyScheduler
from shabetz.services.calendar_feed import _fold, render_ics
from tests.factories import job, params, person, requirement, template

D1 = date(2026, 10, 1)
DAY = (template(1, "Day", 8.0),)


def test_a_lapsed_skill_stops_counting_on_the_day_after_it_expires() -> None:
    medic = replace(person(1, skills={7: 1}), skill_expiry={7: D1})
    result = SimpleGreedyScheduler().generate(
        [medic],
        [job(1, "Ambulance", 1, DAY, (requirement(1, 7, 1),))],
        params(D1, D1 + timedelta(1)),
    )
    assert {a.calendar_date for a in result.assignments} == {D1}


def test_earlier_shifts_send_a_person_to_the_back_of_the_queue() -> None:
    people = [person(1), person(2)]
    jobs = [job(1, "Desk", 1, DAY)]
    fresh = SimpleGreedyScheduler().generate(people, jobs, params(D1, D1))
    assert fresh.assignments[0].person_id == 1  # the tie-break by id

    carried = SimpleGreedyScheduler().generate(people, jobs, params(D1, D1), prior_load={1: 3})
    assert carried.assignments[0].person_id == 2


def _shift(start: float, end: float) -> dict:
    return {
        "job_id": 1,
        "template_id": 2,
        "calendar_date": "2026-10-01",
        "person_id": 3,
        "job_name": "Gate, north",
        "template_name": "Night",
        "start_abs": start,
        "end_abs": end,
    }


def test_shifts_are_written_in_utc_from_the_organisations_wall_clock() -> None:
    ics = render_ics(
        calendar_name="Unit 7",
        schedule_start=D1,
        time_zone="Asia/Jerusalem",  # UTC+3 in October
        assignments=[_shift(22.0, 30.0)],
        generated_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    assert "DTSTART:20261001T190000Z" in ics
    assert "DTEND:20261002T030000Z" in ics
    # Commas are escaped, lines end in CRLF, and the event id stays the same
    # when the schedule is published again.
    assert "SUMMARY:Gate\\, north · Night" in ics
    assert "UID:1-2-2026-10-01-3@shabetz" in ics
    assert ics.endswith("END:VCALENDAR\r\n") and "\r\n" in ics


def test_long_lines_are_folded_within_75_octets() -> None:
    line = "SUMMARY:" + "שבצ״נ " * 40
    folded = _fold(line)
    assert all(len(piece.encode()) <= 75 for piece in folded)
    assert "".join(piece[1:] if i else piece for i, piece in enumerate(folded)) == line
