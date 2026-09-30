"""Editing a schedule after the engine has produced it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from shabetz.domain.enums import ProjectRole
from tests.integration.conftest import Actor, make_member, sign_in

WORKDAYS = [0, 1, 2, 3, 4, 5, 6]
DAY = {"name": "Day", "start_hour": 8.0, "duration_hours": 8.0}
EVENING = {"name": "Evening", "start_hour": 16.0, "duration_hours": 8.0}


def _person(admin: Actor, division: int, name: str, days: list[int] = WORKDAYS) -> int:
    response = admin.post(
        "/api/config/people",
        json={"full_name": name, "division_id": division, "working_weekdays": days},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def world(admin: Actor) -> dict:
    division = admin.post("/api/config/divisions", json={"name": "Alpha"}).json()["id"]
    day = admin.post("/api/config/shift-templates", json=DAY).json()["id"]
    evening = admin.post("/api/config/shift-templates", json=EVENING).json()["id"]
    ana = _person(admin, division, "Ana")
    ben = _person(admin, division, "Ben")
    cat = _person(admin, division, "Cat")
    job = admin.post(
        "/api/config/jobs",
        json={
            "name": "Desk",
            "required_people_per_shift": 1,
            "shift_template_ids": [day, evening],
            "requirements": [],
        },
    ).json()["id"]
    run = admin.post(
        "/api/schedule/generate", json={"start_date": "2026-10-05", "end_date": "2026-10-06"}
    ).json()
    return {
        "division": division,
        "day": day,
        "evening": evening,
        "people": {"Ana": ana, "Ben": ben, "Cat": cat},
        "job": job,
        "run": run,
    }


def _slot(world: dict, template: str, date: str = "2026-10-05") -> dict:
    return {"job_id": world["job"], "template_id": world[template], "calendar_date": date}


def _holder(run: dict, world: dict, template: str, date: str = "2026-10-05") -> dict:
    return next(
        a
        for a in run["assignments"]
        if a["template_id"] == world[template] and a["calendar_date"] == date
    )


def _free_person(run: dict, world: dict, date: str = "2026-10-05") -> int:
    """Someone with no shift at all that day, so swapping them in is conflict-free."""
    busy = {a["person_id"] for a in run["assignments"] if a["calendar_date"] == date}
    return next(pid for pid in world["people"].values() if pid not in busy)


def _url(world: dict, suffix: str = "") -> str:
    return f"/api/schedule/runs/{world['run']['schedule_id']}/assignments{suffix}"


def test_reassigning_a_shift_changes_who_works_it_and_persists(admin: Actor, world: dict) -> None:
    holder = _holder(world["run"], world, "day")
    target = _free_person(world["run"], world)

    response = admin.put(
        _url(world),
        json={**_slot(world, "day"), "from_person_id": holder["person_id"], "to_person_id": target},
    )
    assert response.status_code == 200, response.text
    edited = _holder(response.json(), world, "day")
    assert edited["person_id"] == target
    assert edited["is_manual"] is True

    reloaded = admin.get(f"/api/schedule/runs/{world['run']['schedule_id']}").json()
    assert _holder(reloaded, world, "day")["person_id"] == target


def test_untouched_run_is_unchanged_by_a_no_op_recompute(admin: Actor, world: dict) -> None:
    """Editing one shift must not disturb the warnings of the others."""
    before = world["run"]
    holder = _holder(before, world, "day")
    target = _free_person(before, world)
    after = admin.put(
        _url(world),
        json={**_slot(world, "day"), "from_person_id": holder["person_id"], "to_person_id": target},
    ).json()
    assert after["summary"]["total_assignments"] == before["summary"]["total_assignments"]
    assert [
        w["kind"] for w in after["warnings"] if w["kind"] in ("UNDERSTAFFED", "MISSING_ROLE")
    ] == [w["kind"] for w in before["warnings"] if w["kind"] in ("UNDERSTAFFED", "MISSING_ROLE")]


def test_conflicting_change_needs_acknowledgement(admin: Actor, world: dict) -> None:
    day_holder = _holder(world["run"], world, "day")
    evening_holder = _holder(world["run"], world, "evening")
    # Put the day-shift worker on the evening shift too: back to back, no rest.
    body = {
        **_slot(world, "evening"),
        "from_person_id": evening_holder["person_id"],
        "to_person_id": day_holder["person_id"],
    }

    check = admin.post(
        _url(world, "/check"),
        json={
            **_slot(world, "evening"),
            "person_id": day_holder["person_id"],
            "replaces_person_id": evening_holder["person_id"],
        },
    )
    kinds = {c["kind"] for c in check.json()["conflicts"]}
    assert kinds & {"REST_VIOLATION", "DOUBLE_BOOKED"}

    refused = admin.put(_url(world), json=body)
    assert refused.status_code == 409
    assert refused.json()["code"] == "SCHEDULE_CONFLICT"
    # Refused means nothing was saved.
    reloaded = admin.get(f"/api/schedule/runs/{world['run']['schedule_id']}").json()
    assert _holder(reloaded, world, "evening")["person_id"] == evening_holder["person_id"]

    accepted = admin.put(_url(world), json={**body, "acknowledge_conflicts": True})
    assert accepted.status_code == 200
    kinds_after = {w["kind"] for w in accepted.json()["warnings"]}
    # Accepted conflicts stay visible on the schedule.
    assert kinds_after & {"REST_VIOLATION", "DOUBLE_BOOKED"}


def test_removing_a_person_reports_understaffing(admin: Actor, world: dict) -> None:
    holder = _holder(world["run"], world, "day")
    response = admin.delete(
        _url(world),
        params={**_slot(world, "day"), "person_id": holder["person_id"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["total_assignments"] == world["run"]["summary"]["total_assignments"] - 1
    assert any(
        w["kind"] == "UNDERSTAFFED"
        and w["template_id"] == world["day"]
        and w["calendar_date"] == "2026-10-05"
        for w in body["warnings"]
    )
    assert body["summary"]["understaffed_shift_count"] >= 1


def test_adding_a_person_to_a_full_shift(admin: Actor, world: dict) -> None:
    extra = _free_person(world["run"], world)
    response = admin.post(
        _url(world), json={**_slot(world, "day"), "person_id": extra, "acknowledge_conflicts": True}
    )
    assert response.status_code == 201, response.text
    on_shift = [
        a
        for a in response.json()["assignments"]
        if a["template_id"] == world["day"] and a["calendar_date"] == "2026-10-05"
    ]
    assert len(on_shift) == 2

    duplicate = admin.post(
        _url(world), json={**_slot(world, "day"), "person_id": extra, "acknowledge_conflicts": True}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CONFLICT"


def test_person_on_approved_time_off_is_flagged(admin: Actor, world: dict) -> None:
    holder = _holder(world["run"], world, "day")
    target = _free_person(world["run"], world)
    request = admin.post(
        "/api/time-off",
        json={"person_id": target, "start_date": "2026-10-05", "end_date": "2026-10-05"},
    ).json()
    # Created by a reviewer, so it is already approved.
    assert request["status"] == "APPROVED"

    check = admin.post(
        _url(world, "/check"),
        json={
            **_slot(world, "day"),
            "person_id": target,
            "replaces_person_id": holder["person_id"],
        },
    )
    assert "UNAVAILABLE" in {c["kind"] for c in check.json()["conflicts"]}


def test_unknown_slot_or_person_is_refused(admin: Actor, world: dict) -> None:
    holder = _holder(world["run"], world, "day")
    bad_date = admin.post(
        _url(world),
        json={**_slot(world, "day", "2027-01-01"), "person_id": holder["person_id"]},
    )
    assert bad_date.status_code == 422
    missing = admin.post(
        _url(world),
        json={**_slot(world, "day"), "person_id": 99999},
    )
    assert missing.status_code == 404


def test_staff_cannot_edit_a_schedule(
    client: TestClient,
    admin: Actor,
    world: dict,
    session_factory: sessionmaker[Session],
) -> None:
    make_member(session_factory, admin.project_id, "staff@example.com", ProjectRole.STAFF)
    staff = sign_in(client, "staff@example.com", admin.project_id)
    holder = _holder(world["run"], world, "day")
    response = staff.delete(
        _url(world),
        params={**_slot(world, "day"), "person_id": holder["person_id"]},
    )
    assert response.status_code == 403


def test_collaborator_can_edit(
    client: TestClient,
    admin: Actor,
    world: dict,
    session_factory: sessionmaker[Session],
) -> None:
    make_member(session_factory, admin.project_id, "mgr@example.com", ProjectRole.COLLABORATOR)
    manager = sign_in(client, "mgr@example.com", admin.project_id)
    holder = _holder(world["run"], world, "day")
    response = manager.delete(
        _url(world),
        params={**_slot(world, "day"), "person_id": holder["person_id"]},
    )
    assert response.status_code == 200, response.text


def test_suggestions_offer_free_people_first(admin: Actor, world: dict) -> None:
    holder = _holder(world["run"], world, "day")
    free = _free_person(world["run"], world)
    response = admin.get(
        f"/api/schedule/runs/{world['run']['schedule_id']}/suggestions",
        params={**_slot(world, "day"), "replaces_person_id": holder["person_id"]},
    )
    assert response.status_code == 200, response.text
    ranked = response.json()
    assert ranked[0]["person_id"] == free
    assert ranked[0]["conflicts"] == []
    # The person being replaced is not offered to themselves.
    assert holder["person_id"] not in {r["person_id"] for r in ranked}
    conflict_counts = [len(r["conflicts"]) for r in ranked]
    assert conflict_counts == sorted(conflict_counts)
