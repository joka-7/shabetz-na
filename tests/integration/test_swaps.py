"""Staff hand shifts to colleagues; a manager signs off."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from shabetz.domain.enums import ProjectRole
from tests.integration.conftest import (
    Actor,
    _free_person,
    _holder,
    _slot,
    make_member,
    sign_in,
)


def _setup(client: TestClient, admin: Actor, world: dict, factory: sessionmaker[Session]):
    """Publish, then make staff accounts for the day-shift holder and someone free that day."""
    run_id = world["run"]["schedule_id"]
    holder = _holder(world["run"], world, "day")["person_id"]
    colleague = _free_person(world["run"], world)
    make_member(factory, admin.project_id, "holder@example.com", ProjectRole.STAFF, holder)
    make_member(factory, admin.project_id, "colleague@example.com", ProjectRole.STAFF, colleague)
    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.post(f"/api/schedule/runs/{run_id}/publish", json={}).status_code == 200
    return run_id, holder, colleague


def test_a_swap_needs_the_colleague_and_then_a_manager(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    run_id, holder, colleague = _setup(client, admin, world, session_factory)

    requester = sign_in(client, "holder@example.com", admin.project_id)
    assert colleague in {c["person_id"] for c in requester.get("/api/swaps/colleagues").json()}
    created = requester.post(
        "/api/swaps", json={**_slot(world, "day"), "to_person_id": colleague, "note": "Dentist"}
    )
    assert created.status_code == 201, created.text
    swap = created.json()
    assert swap["status"] == "AWAITING_COLLEAGUE" and swap["can_cancel"]

    # Only the colleague can answer, and a manager cannot decide before they do.
    assert requester.post(f"/api/swaps/{swap['id']}/accept").status_code == 403
    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.post(f"/api/swaps/{swap['id']}/approve", json={}).status_code == 409

    friend = sign_in(client, "colleague@example.com", admin.project_id)
    assert friend.get("/api/swaps").json()[0]["can_accept"] is True
    accepted = friend.post(f"/api/swaps/{swap['id']}/accept")
    assert accepted.json()["status"] == "AWAITING_MANAGER"
    assert friend.post(f"/api/swaps/{swap['id']}/approve", json={}).status_code == 403

    manager = sign_in(client, "admin@example.com", admin.project_id)
    assert manager.get(f"/api/swaps/{swap['id']}/conflicts").json() == []
    approved = manager.post(f"/api/swaps/{swap['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    run = manager.get(f"/api/schedule/runs/{run_id}").json()
    assert _holder(run, world, "day")["person_id"] == colleague
    assert _holder(run, world, "day")["is_manual"] is True
    # The swap is on the record and can be undone like any other edit.
    actions = [e["action"] for e in manager.get(f"/api/schedule/runs/{run_id}/history").json()]
    assert "reassign" in actions


def test_declined_and_cancelled_swaps_change_nothing(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    run_id, holder, colleague = _setup(client, admin, world, session_factory)
    requester = sign_in(client, "holder@example.com", admin.project_id)
    first = requester.post(
        "/api/swaps", json={**_slot(world, "day"), "to_person_id": colleague}
    ).json()
    # One open request per shift.
    assert (
        requester.post(
            "/api/swaps", json={**_slot(world, "day"), "to_person_id": colleague}
        ).status_code
        == 409
    )
    assert requester.post(f"/api/swaps/{first['id']}/cancel").json()["status"] == "CANCELLED"

    second = requester.post(
        "/api/swaps", json={**_slot(world, "day"), "to_person_id": colleague}
    ).json()
    friend = sign_in(client, "colleague@example.com", admin.project_id)
    assert friend.post(f"/api/swaps/{second['id']}/decline").json()["status"] == "DECLINED"

    manager = sign_in(client, "admin@example.com", admin.project_id)
    run = manager.get(f"/api/schedule/runs/{run_id}").json()
    assert _holder(run, world, "day")["person_id"] == holder


def test_only_your_own_published_shift_can_be_offered(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    _, holder, colleague = _setup(client, admin, world, session_factory)
    friend = sign_in(client, "colleague@example.com", admin.project_id)
    # The colleague does not work the day shift on the 5th, so it is not theirs to give.
    response = friend.post("/api/swaps", json={**_slot(world, "day"), "to_person_id": holder})
    assert response.status_code == 404


def test_a_manager_must_acknowledge_a_swap_that_breaks_a_rule(
    client: TestClient, admin: Actor, world: dict, session_factory: sessionmaker[Session]
) -> None:
    run_id, holder, _ = _setup(client, admin, world, session_factory)
    # Hand the day shift to whoever works the evening shift: back to back, no rest.
    evening = _holder(world["run"], world, "evening")["person_id"]
    make_member(
        session_factory, admin.project_id, "evening@example.com", ProjectRole.STAFF, evening
    )
    requester = sign_in(client, "holder@example.com", admin.project_id)
    swap = requester.post(
        "/api/swaps", json={**_slot(world, "day"), "to_person_id": evening}
    ).json()
    sign_in(client, "evening@example.com", admin.project_id).post(f"/api/swaps/{swap['id']}/accept")

    manager = sign_in(client, "admin@example.com", admin.project_id)
    kinds = {c["kind"] for c in manager.get(f"/api/swaps/{swap['id']}/conflicts").json()}
    assert kinds & {"REST_VIOLATION", "DOUBLE_BOOKED"}
    refused = manager.post(f"/api/swaps/{swap['id']}/approve", json={})
    assert refused.status_code == 409 and refused.json()["code"] == "SCHEDULE_CONFLICT"
    ok = manager.post(f"/api/swaps/{swap['id']}/approve", json={"acknowledge_conflicts": True})
    assert ok.status_code == 200
    assert run_id
