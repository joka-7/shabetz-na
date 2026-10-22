"""Viewers, calendar feeds, the inbox counts and the activity log."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from shabetz.config import Settings
from shabetz.domain.enums import ProjectRole
from tests.integration.conftest import Actor, _free_person, _holder, _slot, make_member, sign_in


def test_a_viewer_sees_everything_and_changes_nothing(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    run_id = world["run"]["schedule_id"]
    make_member(session_factory, admin.project_id, "viewer@example.com", ProjectRole.VIEWER)
    viewer = sign_in(client, "viewer@example.com", admin.project_id)

    # Drafts, history and the whole roster, with qualifications.
    assert viewer.get("/api/schedule/runs").status_code == 200
    assert viewer.get(f"/api/schedule/runs/{run_id}").json()["assignments"]
    # Edit history is a manager's tool.
    assert viewer.get(f"/api/schedule/runs/{run_id}/history").status_code == 403
    assert viewer.get("/api/config/people").json()[0]["working_weekdays"]
    assert viewer.get("/api/config/feasibility").status_code == 200

    # No writes of any kind.
    dates = {"start_date": "2026-10-05", "end_date": "2026-10-06"}
    assert viewer.post("/api/schedule/generate", json=dates).status_code == 403
    assert viewer.post(f"/api/schedule/runs/{run_id}/publish", json={}).status_code == 403
    assert viewer.post("/api/config/divisions", json={"name": "X"}).status_code == 403
    holder = _holder(world["run"], world, "day")
    remove = viewer.delete(
        f"/api/schedule/runs/{run_id}/assignments",
        params={**_slot(world, "day"), "person_id": holder["person_id"]},
    )
    assert remove.status_code == 403


def test_a_calendar_feed_shows_the_members_published_shifts(
    client: TestClient,
    admin: Actor,
    world: dict,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    run_id = world["run"]["schedule_id"]
    holder = _holder(world["run"], world, "day")["person_id"]
    make_member(session_factory, admin.project_id, "staff@example.com", ProjectRole.STAFF, holder)
    staff = sign_in(client, "staff@example.com", admin.project_id)
    path = staff.post("/api/me/calendar").json()["path"]
    assert staff.get("/api/me/calendar").json() == {"enabled": True, "path": None}

    client.cookies.clear()  # calendar apps never sign in
    empty = client.get(path)
    assert empty.status_code == 200 and "BEGIN:VEVENT" not in empty.text

    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.post(f"/api/schedule/runs/{run_id}/publish", json={}).status_code == 200
    client.cookies.clear()
    feed = client.get(path)
    assert feed.headers["content-type"].startswith("text/calendar")
    assert feed.text.count("BEGIN:VEVENT") == sum(
        1 for a in world["run"]["assignments"] if a["person_id"] == holder
    )

    # A new address retires the old one; turning it off retires both.
    staff = sign_in(client, "staff@example.com", admin.project_id)
    newer = staff.post("/api/me/calendar").json()["path"]
    client.cookies.clear()
    assert client.get(path).status_code == 404
    assert client.get(newer).status_code == 200

    # Leaving the allowlist ends the feed, as it ends sessions.
    settings.allowed_emails = "admin@example.com"
    assert client.get(newer).status_code == 404


def test_the_inbox_counts_what_waits_on_each_member(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    run_id = world["run"]["schedule_id"]
    holder = _holder(world["run"], world, "day")["person_id"]
    colleague = _free_person(world["run"], world)
    make_member(session_factory, admin.project_id, "holder@example.com", ProjectRole.STAFF, holder)
    make_member(
        session_factory, admin.project_id, "colleague@example.com", ProjectRole.STAFF, colleague
    )
    assert admin.post(f"/api/schedule/runs/{run_id}/publish", json={}).status_code == 200

    requester = sign_in(client, "holder@example.com", admin.project_id)
    requester.post("/api/swaps", json={**_slot(world, "day"), "to_person_id": colleague})
    requester.post("/api/time-off", json={"start_date": "2026-11-01", "end_date": "2026-11-01"})
    assert requester.get("/api/inbox").json() == {"swaps": 0, "time_off": 0}

    friend = sign_in(client, "colleague@example.com", admin.project_id)
    assert friend.get("/api/inbox").json() == {"swaps": 1, "time_off": 0}

    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.get("/api/inbox").json() == {"swaps": 0, "time_off": 1}


def test_the_activity_log_is_for_administrators(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    entries = admin.get("/api/project/activity?limit=2").json()
    assert len(entries) == 2 and entries[0]["id"] > entries[1]["id"]
    assert entries[0]["user_name"] == "First Admin"
    older = admin.get(f"/api/project/activity?before={entries[-1]['id']}").json()
    assert older and older[0]["id"] < entries[-1]["id"]

    make_member(session_factory, admin.project_id, "collab@example.com", ProjectRole.COLLABORATOR)
    collaborator = sign_in(client, "collab@example.com", admin.project_id)
    assert collaborator.get("/api/project/activity").status_code == 403


def test_a_skill_can_carry_an_expiry_date(admin: Actor) -> None:
    division = admin.post("/api/config/divisions", json={"name": "D"}).json()["id"]
    level = admin.post("/api/config/proficiency-levels", json={"name": "L", "rank": 1}).json()
    skill = admin.post("/api/config/skills", json={"name": "Medic"}).json()["id"]
    created = admin.post(
        "/api/config/people",
        json={
            "full_name": "P",
            "division_id": division,
            "skills": [{"skill_id": skill, "level_id": level["id"], "expires_on": "2026-12-31"}],
        },
    )
    assert created.json()["skills"][0]["expires_on"] == "2026-12-31"
