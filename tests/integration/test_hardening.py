"""The fixes from the October 2026 audit, each pinned by a test."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from shabetz.config import Settings
from shabetz.db import models as orm
from shabetz.db.base import utcnow
from shabetz.domain.enums import ProjectRole
from shabetz.services.maintenance import cleanup
from shabetz.services.schedule_edit import ScheduleEditor, SlotKey
from tests.integration.conftest import (
    ADMIN_PASSWORD,
    Actor,
    _free_person,
    _holder,
    _slot,
    make_member,
    sign_in,
)

# ----------------------------------------------------------- client address


def _fresh_throttle(client: TestClient) -> None:
    """Rebuilt on next use with the limits the test just set."""
    client.app.state.login_throttle = None  # type: ignore[attr-defined]


def test_a_forged_forwarded_header_does_not_dodge_the_sign_in_throttle(
    client: TestClient, admin: Actor, settings: Settings
) -> None:
    # As on Render: one proxy, which appends the real address last.
    settings.trusted_proxy_hops = 1
    settings.login_ip_max_failures = 3
    _fresh_throttle(client)
    client.cookies.clear()
    for attempt in range(3):
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "wrong-password-here"},
            # A fresh made-up address each time, then the proxy's real one.
            headers={"x-forwarded-for": f"10.0.0.{attempt}, 203.0.113.7"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
        headers={"x-forwarded-for": "10.0.0.99, 203.0.113.7"},
    )
    assert blocked.status_code == 429


def test_the_real_address_is_counted_separately_from_others(
    client: TestClient, admin: Actor, settings: Settings
) -> None:
    settings.trusted_proxy_hops = 1
    settings.login_ip_max_failures = 2
    _fresh_throttle(client)
    client.cookies.clear()
    for _ in range(2):
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "wrong-password-here"},
            headers={"x-forwarded-for": "203.0.113.7"},
        )
    other = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
        headers={"x-forwarded-for": "198.51.100.1"},
    )
    assert other.status_code == 200


# ------------------------------------------------------------- generation


def test_a_schedule_longer_than_the_limit_is_refused(admin: Actor, settings: Settings) -> None:
    settings.max_schedule_days = 31
    response = admin.post(
        "/api/schedule/generate", json={"start_date": "2026-10-01", "end_date": "2026-11-01"}
    )
    assert response.status_code == 422
    assert "at most 31 days" in response.json()["detail"]


# -------------------------------------------------------- concurrent edits


def test_two_editors_saving_the_same_schedule_cannot_both_win(
    world: dict, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    run_id = world["run"]["schedule_id"]
    holder = _holder(world["run"], world, "day")
    key = SlotKey(world["job"], world["day"], date.fromisoformat(holder["calendar_date"]))
    free = _free_person(world["run"], world)

    first, second = session_factory(), session_factory()
    try:
        one = ScheduleEditor(first, admin.project_id, first.get(orm.ScheduleRun, run_id))
        two = ScheduleEditor(second, admin.project_id, second.get(orm.ScheduleRun, run_id))
        one.remove(key, holder["person_id"])
        two.reassign(key, holder["person_id"], free)
        one.save()
        first.commit()
        with pytest.raises(StaleDataError):
            two.save()
    finally:
        first.close()
        second.close()


# ----------------------------------------------------------------- swaps


def _swap(client: TestClient, admin: Actor, world: dict, factory: sessionmaker[Session]) -> int:
    run_id = world["run"]["schedule_id"]
    holder = _holder(world["run"], world, "day")["person_id"]
    colleague = _free_person(world["run"], world)
    make_member(factory, admin.project_id, "holder@example.com", ProjectRole.STAFF, holder)
    make_member(factory, admin.project_id, "colleague@example.com", ProjectRole.STAFF, colleague)
    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.post(f"/api/schedule/runs/{run_id}/publish", json={}).status_code == 200
    requester = sign_in(client, "holder@example.com", admin.project_id)
    swap = requester.post(
        "/api/swaps", json={**_slot(world, "day"), "to_person_id": colleague}
    ).json()
    friend = sign_in(client, "colleague@example.com", admin.project_id)
    assert friend.post(f"/api/swaps/{swap['id']}/accept").status_code == 200
    return int(swap["id"])


def test_publishing_another_schedule_closes_swaps_on_the_old_one(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    swap_id = _swap(client, admin, world, session_factory)
    manager = sign_in(client, "admin@example.com", admin.project_id)
    newer = manager.post(
        "/api/schedule/generate", json={"start_date": "2026-10-05", "end_date": "2026-10-06"}
    ).json()["schedule_id"]
    assert manager.post(f"/api/schedule/runs/{newer}/publish", json={}).status_code == 200

    swap = next(s for s in manager.get("/api/swaps").json() if s["id"] == swap_id)
    assert swap["status"] == "CANCELLED"
    assert manager.post(f"/api/swaps/{swap_id}/approve", json={}).status_code == 409


def test_a_swap_cannot_be_approved_against_an_unpublished_schedule(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    swap_id = _swap(client, admin, world, session_factory)
    # Put the request back to waiting, as it would be had it slipped past the
    # cancellation, to check the approval itself refuses.
    manager = sign_in(client, "admin@example.com", admin.project_id)
    run_id = world["run"]["schedule_id"]
    assert manager.post(f"/api/schedule/runs/{run_id}/unpublish").status_code == 200
    with session_factory() as db:
        row = db.get(orm.SwapRequest, swap_id)
        assert row is not None and row.status.value == "CANCELLED"
        row.status = row.status.__class__("AWAITING_MANAGER")
        db.commit()
    assert manager.post(f"/api/swaps/{swap_id}/approve", json={}).status_code == 409


# ----------------------------------------------------------- staff scoping


def test_staff_see_names_but_not_qualifications(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    make_member(session_factory, admin.project_id, "staff@example.com", ProjectRole.STAFF)
    staff = sign_in(client, "staff@example.com", admin.project_id)
    people = staff.get("/api/config/people").json()
    assert {p["full_name"] for p in people} == {"Ana", "Ben", "Cat"}
    assert all(p["working_weekdays"] == [] and p["skills"] == [] for p in people)
    assert staff.get("/api/config/feasibility").status_code == 403

    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.get("/api/config/people").json()[0]["working_weekdays"]


# ---------------------------------------------------------------- headers


def test_responses_carry_security_headers(client: TestClient) -> None:
    response = client.get("/api/meta/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    # The test server is plain http, where insisting on HTTPS would lock it out.
    assert "strict-transport-security" not in response.headers


# --------------------------------------------------------------- sessions


def test_only_a_hash_of_the_session_token_is_stored(
    client: TestClient, admin: Actor, session_factory: sessionmaker[Session], settings: Settings
) -> None:
    token = client.cookies.get(settings.cookie_name)
    assert token
    with session_factory() as db:
        ids = set(db.scalars(select(orm.Session.id)))
    assert token not in ids
    assert hashlib.sha256(token.encode()).hexdigest() in ids


def test_cleanup_removes_long_dead_sessions_and_keeps_live_ones(
    admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as db:
        user_id = db.scalars(select(orm.User.id)).first()
        db.add(
            orm.Session(
                id="old",
                user_id=user_id,
                csrf_token="x",
                expires_at=utcnow() - timedelta(days=60),
            )
        )
        db.commit()
        report = cleanup(db)
        db.commit()
        ids = set(db.scalars(select(orm.Session.id)))
    assert report.sessions == 1
    assert "old" not in ids and len(ids) == 1
    assert admin.get("/api/auth/me").status_code == 200


# ------------------------------------------------------------------ skills


def test_a_skill_can_be_deleted_once_no_job_requires_it(admin: Actor) -> None:
    division = admin.post("/api/config/divisions", json={"name": "D"}).json()["id"]
    level = admin.post("/api/config/proficiency-levels", json={"name": "L", "rank": 1}).json()
    skill = admin.post("/api/config/skills", json={"name": "Medic"}).json()["id"]
    template = admin.post(
        "/api/config/shift-templates", json={"name": "T", "start_hour": 0, "duration_hours": 8}
    ).json()["id"]
    person = admin.post(
        "/api/config/people",
        json={
            "full_name": "P",
            "division_id": division,
            "skills": [{"skill_id": skill, "level_id": level["id"]}],
        },
    ).json()
    job = admin.post(
        "/api/config/jobs",
        json={
            "name": "J",
            "required_people_per_shift": 1,
            "shift_template_ids": [template],
            "requirements": [{"skill_id": skill, "min_level_id": level["id"]}],
        },
    )
    assert job.status_code == 201, job.text

    refused = admin.delete(f"/api/config/skills/{skill}")
    assert refused.status_code == 409 and "still required" in refused.json()["detail"]

    assert admin.delete(f"/api/config/jobs/{job.json()['id']}").status_code == 204
    assert admin.delete(f"/api/config/skills/{skill}").status_code == 204
    assert skill not in {s["id"] for s in admin.get("/api/config/skills").json()}
    people = admin.get("/api/config/people").json()
    assert next(p for p in people if p["id"] == person["id"])["skills"] == []


# ------------------------------------------------------------------ people


def test_removing_a_person_closes_what_waits_on_them(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    swap_id = _swap(client, admin, world, session_factory)
    holder = _holder(world["run"], world, "day")["person_id"]
    requester = sign_in(client, "holder@example.com", admin.project_id)
    pending = requester.post(
        "/api/time-off", json={"start_date": "2026-11-01", "end_date": "2026-11-02"}
    ).json()

    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.delete(f"/api/config/people/{holder}").status_code == 204

    with session_factory() as db:
        assert db.get(orm.SwapRequest, swap_id).status.value == "CANCELLED"  # type: ignore[union-attr]
        assert db.get(orm.TimeOff, pending["id"]).status.value == "CANCELLED"  # type: ignore[union-attr]
        linked = db.scalars(
            select(orm.ProjectMember).where(orm.ProjectMember.person_id == holder)
        ).all()
    assert linked == []


# ---------------------------------------------------------------- time off


def test_approving_time_off_names_the_published_shifts_it_leaves_uncovered(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    run_id = world["run"]["schedule_id"]
    holder = _holder(world["run"], world, "day")
    make_member(
        session_factory,
        admin.project_id,
        "holder@example.com",
        ProjectRole.STAFF,
        holder["person_id"],
    )
    assert admin.post(f"/api/schedule/runs/{run_id}/publish", json={}).status_code == 200

    staff = sign_in(client, "holder@example.com", admin.project_id)
    request = staff.post(
        "/api/time-off",
        json={"start_date": holder["calendar_date"], "end_date": holder["calendar_date"]},
    ).json()
    assert request["published_shifts"] == []

    manager = sign_in(client, "admin@example.com", admin.project_id)
    approved = manager.post(f"/api/time-off/{request['id']}/approve", json={}).json()
    assert approved["status"] == "APPROVED"
    assert {s["calendar_date"] for s in approved["published_shifts"]} == {holder["calendar_date"]}


# ---------------------------------------------------------------- settings


def test_an_unknown_time_zone_is_refused(admin: Actor) -> None:
    current = admin.get("/api/config/settings").json()
    bad = admin.put("/api/config/settings", json={**current, "timezone": "Mars/Olympus"})
    assert bad.status_code == 422
    good = admin.put("/api/config/settings", json={**current, "timezone": "Asia/Jerusalem"})
    assert good.status_code == 200 and good.json()["timezone"] == "Asia/Jerusalem"


# ----------------------------------------------------------------- invites


def test_hammering_invite_links_is_throttled(client: TestClient) -> None:
    for _ in range(30):
        assert client.get("/api/invites/not-a-real-token").status_code == 404
    assert client.get("/api/invites/not-a-real-token").status_code == 429


# --------------------------------------------------------------- allowlist


def test_only_listed_addresses_get_in(
    client: TestClient, admin: Actor, settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    from tests.integration.conftest import make_account

    make_account(session_factory, "stranger@example.com")
    settings.allowed_emails = " Admin@Example.com "

    assert sign_in(client, "admin@example.com").get("/api/auth/me").status_code == 200
    client.cookies.clear()
    refused = client.post(
        "/api/auth/login", json={"email": "stranger@example.com", "password": ADMIN_PASSWORD}
    )
    # The same answer as a wrong password: the list cannot be probed.
    assert refused.status_code == 401
    assert refused.json()["detail"] == "Invalid email or password"


def test_taking_an_address_off_the_list_ends_its_sessions(admin: Actor, settings: Settings) -> None:
    assert admin.get("/api/auth/me").status_code == 200
    settings.allowed_emails = "someone-else@example.com"
    assert admin.get("/api/auth/me").status_code == 401


def test_an_empty_list_lets_nobody_into_a_production_server(
    client: TestClient, admin: Actor, settings: Settings
) -> None:
    settings.environment = "prod"
    settings.allowed_emails = ""
    client.cookies.clear()
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 401
    settings.allowed_emails = "*"
    response = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200


def test_withdrawing_a_draft_leaves_the_published_schedules_swaps_open(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    swap_id = _swap(client, admin, world, session_factory)
    manager = sign_in(client, "admin@example.com", admin.project_id)
    draft = manager.post(
        "/api/schedule/generate", json={"start_date": "2026-10-05", "end_date": "2026-10-06"}
    ).json()["schedule_id"]
    assert manager.post(f"/api/schedule/runs/{draft}/unpublish").status_code == 200
    swap = next(s for s in manager.get("/api/swaps").json() if s["id"] == swap_id)
    assert swap["status"] == "AWAITING_MANAGER"
