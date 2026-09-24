"""Time off has to actually reach the scheduler.

The approval workflow is only meaningful if approving something changes the
schedule. This was a real bug: enum columns loaded back as plain strings, so
the repository's ``status is APPROVED`` filter silently matched nothing and
approved absence never excluded anyone.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from shabetz.domain.enums import ProjectRole
from tests.integration.conftest import Actor, make_member, sign_in

WORKDAYS = [0, 1, 2, 3, 4, 5, 6]
WINDOW = {"name": "All day", "start_hour": 0.0, "duration_hours": 8.0}


def _minimal_config(admin: Actor) -> dict[str, int]:
    division = admin.post("/api/config/divisions", json={"name": "Alpha"}).json()
    template = admin.post("/api/config/shift-templates", json=WINDOW).json()
    person = admin.post(
        "/api/config/people",
        json={
            "full_name": "Only Person",
            "division_id": division["id"],
            "working_weekdays": WORKDAYS,
        },
    ).json()
    job = admin.post(
        "/api/config/jobs",
        json={
            "name": "Desk",
            "required_people_per_shift": 1,
            "shift_template_ids": [template["id"]],
            "requirements": [],
        },
    ).json()
    return {"person": person["id"], "job": job["id"], "division": division["id"]}


def _generate(admin: Actor, start: str, end: str) -> dict:
    response = admin.post("/api/schedule/generate", json={"start_date": start, "end_date": end})
    assert response.status_code == 201, response.text
    return response.json()


def test_approved_time_off_removes_a_person_from_the_schedule(
    client: TestClient, admin: Actor
) -> None:
    ids = _minimal_config(admin)

    before = _generate(admin, "2026-10-01", "2026-10-03")
    assert before["summary"]["total_assignments"] == 3

    request = admin.post(
        "/api/time-off",
        json={
            "person_id": ids["person"],
            "start_date": "2026-10-02",
            "end_date": "2026-10-02",
        },
    ).json()
    assert request["status"] == "APPROVED"

    after = _generate(admin, "2026-10-01", "2026-10-03")
    dates = sorted(a["calendar_date"] for a in after["assignments"])
    assert dates == ["2026-10-01", "2026-10-03"], "the approved day must be skipped"
    assert after["summary"]["understaffed_shift_count"] == 1


def test_pending_time_off_does_not_change_the_schedule(
    client: TestClient, admin: Actor, session_factory
) -> None:
    """A request still awaiting review must not quietly alter staffing."""
    ids = _minimal_config(admin)

    admin.post(
        "/api/config/people",
        json={
            "full_name": "Another",
            "division_id": ids["division"],
            "working_weekdays": WORKDAYS,
        },
    )
    staff_person = admin.post(
        "/api/config/people",
        json={
            "full_name": "Requester",
            "division_id": ids["division"],
            "working_weekdays": WORKDAYS,
        },
    ).json()

    make_member(
        session_factory,
        admin.project_id,
        "requester@example.com",
        ProjectRole.STAFF,
        staff_person["id"],
    )
    staff = sign_in(TestClient(client.app), "requester@example.com", admin.project_id)

    pending = staff.post(
        "/api/time-off",
        json={"start_date": "2026-10-02", "end_date": "2026-10-02"},
    ).json()
    assert pending["status"] == "PENDING"

    schedule = _generate(admin, "2026-10-02", "2026-10-02")
    assert schedule["summary"]["understaffed_shift_count"] == 0


def test_approving_a_pending_request_then_changes_the_schedule(
    client: TestClient, admin: Actor, session_factory
) -> None:
    ids = _minimal_config(admin)

    make_member(
        session_factory, admin.project_id, "solo@example.com", ProjectRole.STAFF, ids["person"]
    )
    staff = sign_in(TestClient(client.app), "solo@example.com", admin.project_id)

    request = staff.post(
        "/api/time-off", json={"start_date": "2026-10-05", "end_date": "2026-10-05"}
    ).json()

    assert _generate(admin, "2026-10-05", "2026-10-05")["summary"]["understaffed_shift_count"] == 0

    approved = admin.post(f"/api/time-off/{request['id']}/approve", json={}).json()
    assert approved["status"] == "APPROVED"

    assert _generate(admin, "2026-10-05", "2026-10-05")["summary"]["understaffed_shift_count"] == 1


def test_an_already_reviewed_request_cannot_be_reviewed_again(
    client: TestClient, admin: Actor
) -> None:
    """Guarded by a status comparison that the enum bug had made unreachable."""
    ids = _minimal_config(admin)
    request = admin.post(
        "/api/time-off",
        json={
            "person_id": ids["person"],
            "start_date": "2026-10-02",
            "end_date": "2026-10-02",
        },
    ).json()

    # Created by a reviewer, so it is already approved.
    assert admin.post(f"/api/time-off/{request['id']}/approve", json={}).status_code == 422
    assert admin.post(f"/api/time-off/{request['id']}/deny", json={}).status_code == 422


def test_cancelling_approved_time_off_restores_availability(
    client: TestClient, admin: Actor
) -> None:
    ids = _minimal_config(admin)
    request = admin.post(
        "/api/time-off",
        json={
            "person_id": ids["person"],
            "start_date": "2026-10-02",
            "end_date": "2026-10-02",
        },
    ).json()
    assert _generate(admin, "2026-10-02", "2026-10-02")["summary"]["understaffed_shift_count"] == 1

    admin.post(f"/api/time-off/{request['id']}/cancel")
    assert _generate(admin, "2026-10-02", "2026-10-02")["summary"]["understaffed_shift_count"] == 0
