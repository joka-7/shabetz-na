"""Account management.

The bootstrap route closes permanently after the first account, so these are
the only endpoints that can ever produce another one. The rules worth pinning
are the ones that would otherwise make the system unrecoverable.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from shabetz.domain.enums import UserRole
from tests.integration.conftest import Actor

OTHER_PASSWORD = "another-long-enough-password"


def _sign_in(client: TestClient, email: str, password: str) -> Actor:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    return Actor(client, body["csrf_token"], body["user"])


def _invite(admin: Actor, email: str, role: UserRole, **extra: object) -> dict:
    response = admin.post(
        "/api/users",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "role": role.value,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# -------------------------------------------------------------- creating them


def test_admin_can_invite_an_account_that_can_then_sign_in(
    client: TestClient, admin: Actor
) -> None:
    _invite(admin, "scheduler@example.com", UserRole.SCHEDULER, password=OTHER_PASSWORD)

    client.cookies.clear()
    actor = _sign_in(client, "scheduler@example.com", OTHER_PASSWORD)
    assert actor.user["role"] == "SCHEDULER"


def test_invited_account_without_a_password_cannot_sign_in_yet(
    client: TestClient, admin: Actor
) -> None:
    """An account reachable only through Google is visibly not ready for a password."""
    created = _invite(admin, "pending@example.com", UserRole.STAFF)
    assert created["has_password"] is False
    assert created["has_google"] is False

    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/login", json={"email": "pending@example.com", "password": "anything-at-all"}
        ).status_code
        == 401
    )


def test_duplicate_email_is_refused(client: TestClient, admin: Actor) -> None:
    _invite(admin, "dup@example.com", UserRole.STAFF)
    response = admin.post(
        "/api/users",
        json={"email": "dup@example.com", "full_name": "Dup", "role": "STAFF"},
    )
    assert response.status_code == 409


def test_weak_password_is_refused(client: TestClient, admin: Actor) -> None:
    response = admin.post(
        "/api/users",
        json={"email": "weak@example.com", "full_name": "W", "role": "STAFF", "password": "short"},
    )
    assert response.status_code == 422


def test_only_admins_may_manage_accounts(client: TestClient, admin: Actor) -> None:
    _invite(admin, "scheduler@example.com", UserRole.SCHEDULER, password=OTHER_PASSWORD)
    client.cookies.clear()
    scheduler = _sign_in(client, "scheduler@example.com", OTHER_PASSWORD)

    assert scheduler.get("/api/users").status_code == 403
    assert (
        scheduler.post(
            "/api/users",
            json={"email": "x@example.com", "full_name": "X", "role": "ADMIN"},
        ).status_code
        == 403
    )


# ------------------------------------------------------- keeping a way back in


def test_the_last_administrator_cannot_be_demoted(client: TestClient, admin: Actor) -> None:
    """Otherwise nobody could manage the system and bootstrap is long closed."""
    response = admin.put(f"/api/users/{admin.user['id']}", json={"role": "STAFF"})
    assert response.status_code == 409
    assert "only administrator" in response.json()["detail"]


def test_the_last_administrator_cannot_be_deactivated(client: TestClient, admin: Actor) -> None:
    assert admin.put(f"/api/users/{admin.user['id']}", json={"is_active": False}).status_code == 409
    assert admin.delete(f"/api/users/{admin.user['id']}").status_code == 409


def test_an_administrator_may_step_down_once_another_exists(
    client: TestClient, admin: Actor
) -> None:
    second = _invite(admin, "second@example.com", UserRole.ADMIN, password=OTHER_PASSWORD)
    assert admin.put(f"/api/users/{admin.user['id']}", json={"role": "STAFF"}).status_code == 200

    client.cookies.clear()
    remaining = _sign_in(client, "second@example.com", OTHER_PASSWORD)
    assert remaining.user["id"] == second["id"]
    assert remaining.get("/api/users").status_code == 200


# ---------------------------------------------------------- revoking access now


def test_deactivating_an_account_ends_its_session_immediately(
    client: TestClient, admin: Actor
) -> None:
    """A revoked account must not keep working until its session happens to expire."""
    created = _invite(admin, "staff@example.com", UserRole.STAFF, password=OTHER_PASSWORD)

    staff_client = TestClient(client.app)
    staff = _sign_in(staff_client, "staff@example.com", OTHER_PASSWORD)
    assert staff.get("/api/auth/me").status_code == 200

    admin.delete(f"/api/users/{created['id']}")
    assert staff.get("/api/auth/me").status_code == 401


def test_changing_a_role_ends_the_session_so_old_rights_cannot_linger(
    client: TestClient, admin: Actor
) -> None:
    created = _invite(admin, "temp@example.com", UserRole.SCHEDULER, password=OTHER_PASSWORD)

    other_client = TestClient(client.app)
    actor = _sign_in(other_client, "temp@example.com", OTHER_PASSWORD)
    assert actor.get("/api/auth/me").json()["role"] == "SCHEDULER"

    admin.put(f"/api/users/{created['id']}", json={"role": "STAFF"})
    assert actor.get("/api/auth/me").status_code == 401


def test_revoke_sessions_signs_an_account_out_everywhere(client: TestClient, admin: Actor) -> None:
    created = _invite(admin, "busy@example.com", UserRole.STAFF, password=OTHER_PASSWORD)

    first = _sign_in(TestClient(client.app), "busy@example.com", OTHER_PASSWORD)
    second = _sign_in(TestClient(client.app), "busy@example.com", OTHER_PASSWORD)

    admin.post(f"/api/users/{created['id']}/revoke-sessions")
    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401


# ------------------------------------------------------------------- passwords


def test_admin_can_set_a_password_and_it_ends_existing_sessions(
    client: TestClient, admin: Actor
) -> None:
    created = _invite(admin, "reset@example.com", UserRole.STAFF, password=OTHER_PASSWORD)

    existing = _sign_in(TestClient(client.app), "reset@example.com", OTHER_PASSWORD)
    admin.post(f"/api/users/{created['id']}/password", json={"password": "a-brand-new-password"})

    assert existing.get("/api/auth/me").status_code == 401
    fresh = _sign_in(TestClient(client.app), "reset@example.com", "a-brand-new-password")
    assert fresh.user["email"] == "reset@example.com"


def test_setting_a_password_clears_a_lockout(client: TestClient, admin: Actor) -> None:
    """This is how an administrator restores access to someone locked out."""
    created = _invite(admin, "locked@example.com", UserRole.STAFF, password=OTHER_PASSWORD)

    locked_client = TestClient(client.app)
    for _ in range(8):
        locked_client.post(
            "/api/auth/login", json={"email": "locked@example.com", "password": "wrong"}
        )
    assert (
        locked_client.post(
            "/api/auth/login", json={"email": "locked@example.com", "password": OTHER_PASSWORD}
        ).status_code
        == 403
    )

    admin.post(f"/api/users/{created['id']}/password", json={"password": "a-recovered-password"})
    assert admin.get("/api/users").status_code == 200

    recovered = _sign_in(TestClient(client.app), "locked@example.com", "a-recovered-password")
    assert recovered.user["email"] == "locked@example.com"


# ---------------------------------------------------------------- staff link


def test_linking_an_account_to_a_person_scopes_their_view(client: TestClient, admin: Actor) -> None:
    division = admin.post("/api/config/divisions", json={"name": "Alpha"}).json()
    person = admin.post(
        "/api/config/people",
        json={"full_name": "Dana", "division_id": division["id"], "working_weekdays": [0, 1]},
    ).json()

    created = _invite(
        admin, "dana@example.com", UserRole.STAFF, password=OTHER_PASSWORD, person_id=person["id"]
    )
    assert created["person_id"] == person["id"]

    staff = _sign_in(TestClient(client.app), "dana@example.com", OTHER_PASSWORD)
    assert staff.get("/api/auth/me").json()["person_id"] == person["id"]


def test_linking_to_a_missing_person_is_refused(client: TestClient, admin: Actor) -> None:
    response = admin.post(
        "/api/users",
        json={
            "email": "ghost@example.com",
            "full_name": "Ghost",
            "role": "STAFF",
            "person_id": 9999,
        },
    )
    assert response.status_code == 422
