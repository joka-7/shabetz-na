"""Marking who is there, and what a day looks like for each role."""

from __future__ import annotations

from fastapi.testclient import TestClient

from shabetz.domain.enums import ProjectRole
from tests.integration.conftest import Actor, make_member, sign_in

DAY = "2026-10-12"


def _people(admin: Actor, *names: str) -> list[dict]:
    division = admin.post("/api/config/divisions", json={"name": "North"}).json()
    return [
        admin.post(
            "/api/config/people", json={"full_name": name, "division_id": division["id"]}
        ).json()
        for name in names
    ]


def _day(actor: Actor, day: str = DAY) -> dict[str, dict]:
    response = actor.get(f"/api/attendance?date={day}")
    assert response.status_code == 200, response.text
    return {row["full_name"]: row for row in response.json()}


def test_everyone_starts_unmarked(admin: Actor) -> None:
    _people(admin, "Avi", "Dana")
    rows = _day(admin)
    assert set(rows) == {"Avi", "Dana"}
    assert all(row["status"] is None and not row["on_leave"] for row in rows.values())


def test_marking_present_and_absent_with_a_note(admin: Actor) -> None:
    avi, dana = _people(admin, "Avi", "Dana")
    admin.put(
        "/api/attendance", json={"person_id": avi["id"], "calendar_date": DAY, "status": "PRESENT"}
    )
    after = admin.put(
        "/api/attendance",
        json={"person_id": dana["id"], "calendar_date": DAY, "status": "ABSENT", "note": " sick "},
    )
    assert after.status_code == 200, after.text
    rows = {row["full_name"]: row for row in after.json()}
    assert rows["Avi"]["status"] == "PRESENT"
    assert rows["Dana"]["status"] == "ABSENT" and rows["Dana"]["note"] == "sick"
    # Another day is untouched.
    assert _day(admin, "2026-10-13")["Dana"]["status"] is None


def test_a_mark_can_be_changed_and_cleared(admin: Actor) -> None:
    (avi,) = _people(admin, "Avi")
    body = {"person_id": avi["id"], "calendar_date": DAY}
    admin.put("/api/attendance", json={**body, "status": "ABSENT"})
    admin.put("/api/attendance", json={**body, "status": "PRESENT"})
    assert _day(admin)["Avi"]["status"] == "PRESENT"
    admin.put("/api/attendance", json=body)
    assert _day(admin)["Avi"]["status"] is None


def test_everyone_present_leaves_those_already_marked(admin: Actor) -> None:
    avi, dana, lee = _people(admin, "Avi", "Dana", "Lee")
    admin.put(
        "/api/attendance", json={"person_id": dana["id"], "calendar_date": DAY, "status": "ABSENT"}
    )
    response = admin.post("/api/attendance/bulk", json={"calendar_date": DAY})
    assert response.status_code == 200, response.text
    rows = {row["full_name"]: row["status"] for row in response.json()}
    assert rows == {"Avi": "PRESENT", "Dana": "ABSENT", "Lee": "PRESENT"}


def test_approved_leave_is_reported_with_its_reason_to_editors(admin: Actor) -> None:
    (avi,) = _people(admin, "Avi")
    made = admin.post(
        "/api/time-off",
        json={
            "person_id": avi["id"],
            "start_date": "2026-10-11",
            "end_date": "2026-10-13",
            "reason": "Trip",
        },
    ).json()
    # Entered by an editor, so it is approved already.
    assert made["status"] == "APPROVED"
    row = _day(admin)["Avi"]
    assert row["on_leave"] is True and row["leave_reason"] == "Trip"
    assert _day(admin, "2026-10-20")["Avi"]["on_leave"] is False


def test_viewers_read_without_the_reason_and_cannot_mark(
    client: TestClient, admin: Actor, session_factory
) -> None:
    (avi,) = _people(admin, "Avi")
    made = admin.post(
        "/api/time-off",
        json={"person_id": avi["id"], "start_date": DAY, "end_date": DAY, "reason": "Private"},
    ).json()
    assert made["status"] == "APPROVED"
    make_member(session_factory, admin.project_id, "v@example.com", ProjectRole.VIEWER)
    viewer = sign_in(TestClient(client.app), "v@example.com").in_project(admin.project_id)

    row = _day(viewer)["Avi"]
    assert row["on_leave"] is True and row["leave_reason"] is None
    denied = viewer.put(
        "/api/attendance", json={"person_id": avi["id"], "calendar_date": DAY, "status": "PRESENT"}
    )
    assert denied.status_code == 403
    assert viewer.post("/api/attendance/bulk", json={"calendar_date": DAY}).status_code == 403


def test_staff_cannot_see_attendance(client: TestClient, admin: Actor, session_factory) -> None:
    make_member(session_factory, admin.project_id, "s@example.com", ProjectRole.STAFF)
    staff = sign_in(TestClient(client.app), "s@example.com").in_project(admin.project_id)
    assert staff.get(f"/api/attendance?date={DAY}").status_code == 403


def test_attendance_stays_in_its_project(client: TestClient, admin: Actor, session_factory) -> None:
    (avi,) = _people(admin, "Avi")
    admin.put(
        "/api/attendance", json={"person_id": avi["id"], "calendar_date": DAY, "status": "PRESENT"}
    )
    from tests.integration.conftest import make_account

    make_account(session_factory, "other@example.com")
    other = sign_in(TestClient(client.app), "other@example.com")
    mine = other.post("/api/projects", json={"name": "Theirs"}).json()
    other = other.in_project(mine["id"])
    assert other.get(f"/api/attendance?date={DAY}").json() == []
    # A person from another project cannot be marked by id.
    response = other.put(
        "/api/attendance", json={"person_id": avi["id"], "calendar_date": DAY, "status": "ABSENT"}
    )
    assert response.status_code == 404


def test_task_notes_are_saved_and_survive_a_backup(admin: Actor) -> None:
    template = admin.post(
        "/api/config/shift-templates", json={"name": "Day", "start_hour": 8, "duration_hours": 8}
    ).json()
    job = admin.post(
        "/api/config/jobs",
        json={
            "name": "Gate",
            "required_people_per_shift": 2,
            "notes": "  Bring the radio  ",
            "shift_template_ids": [template["id"]],
        },
    )
    assert job.status_code == 201, job.text
    assert job.json()["notes"] == "Bring the radio"

    backup = admin.get(f"/api/config/backup?project={admin.project_id}").json()
    assert backup["jobs"][0]["notes"] == "Bring the radio"

    # A backup from before notes existed must not wipe them.
    del backup["jobs"][0]["notes"]
    admin.post("/api/config/backup/import", json={"backup": backup, "apply": True})
    assert admin.get("/api/config/jobs").json()[0]["notes"] == "Bring the radio"


def test_clearing_a_mark_also_drops_its_reason(admin: Actor) -> None:
    (avi,) = _people(admin, "Avi")
    body = {"person_id": avi["id"], "calendar_date": DAY}
    admin.put("/api/attendance", json={**body, "status": "ABSENT", "note": "Sick"})
    cleared = admin.put("/api/attendance", json={**body, "note": "Sick"})
    assert cleared.status_code == 200
    row = {r["full_name"]: r for r in cleared.json()}["Avi"]
    assert row["status"] is None and row["note"] is None
