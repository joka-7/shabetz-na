"""Authentication, the bootstrap window, CSRF, and per-role authorization."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shabetz.domain.enums import ProjectRole
from tests.integration.conftest import ADMIN_PASSWORD, Actor, make_member, sign_in


def _member(client: TestClient, factory, admin: Actor, role: ProjectRole, person_id=None) -> Actor:  # type: ignore[no-untyped-def]
    if role is ProjectRole.ADMIN and person_id is None:
        return admin
    email = f"{role.value.lower()}@example.com"
    make_member(factory, admin.project_id, email, role, person_id)
    return sign_in(client, email, admin.project_id)


# ------------------------------------------------------------ bootstrap window


def test_setup_status_flips_after_first_admin(client: TestClient) -> None:
    assert client.get("/api/meta/capabilities").json()["setup_complete"] is False
    client.post(
        "/api/setup/bootstrap-admin",
        json={"email": "a@example.com", "full_name": "A", "password": ADMIN_PASSWORD},
    )
    assert client.get("/api/meta/capabilities").json()["setup_complete"] is True


def test_the_first_administrator_gets_a_project_to_run(client: TestClient) -> None:
    client.post(
        "/api/setup/bootstrap-admin",
        json={
            "email": "a@example.com",
            "full_name": "A",
            "password": ADMIN_PASSWORD,
            "organization_name": "Acme",
        },
    )
    projects = client.get("/api/projects").json()
    assert [(p["name"], p["role"]) for p in projects] == [("Acme", "ADMIN")]


def test_bootstrap_is_refused_once_an_account_exists(client: TestClient, admin: Actor) -> None:
    """The unauthenticated window must close permanently after the first admin."""
    second = client.post(
        "/api/setup/bootstrap-admin",
        json={"email": "intruder@example.com", "full_name": "X", "password": ADMIN_PASSWORD},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "CONFLICT"


def test_bootstrap_rejects_a_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/setup/bootstrap-admin",
        json={"email": "a@example.com", "full_name": "A", "password": "short"},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------- sign-in


def test_login_succeeds_and_issues_a_session(client: TestClient, admin: Actor) -> None:
    actor = sign_in(client, "admin@example.com")
    assert actor.user["email"] == "admin@example.com"
    assert client.get("/api/auth/me").json()["email"] == "admin@example.com"


def test_wrong_password_and_unknown_account_are_indistinguishable(
    client: TestClient, admin: Actor
) -> None:
    """Differing responses would confirm which addresses have accounts."""
    wrong = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "not-the-password"}
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "not-the-password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_repeated_failures_lock_the_account(client: TestClient, admin: Actor) -> None:
    for _ in range(8):
        client.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
    locked = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": ADMIN_PASSWORD}
    )
    assert locked.status_code == 403


def test_logout_revokes_the_session_immediately(client: TestClient, admin: Actor) -> None:
    assert admin.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_unauthenticated_requests_are_refused(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/config/divisions").status_code == 401


# ------------------------------------------------------------------------ CSRF


def test_mutation_without_csrf_token_is_refused(client: TestClient, admin: Actor) -> None:
    """Auth rides on a cookie, so a bare cookie must not be enough to write."""
    response = client.post("/api/config/divisions", json={"name": "Alpha"})
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_mutation_with_wrong_csrf_token_is_refused(client: TestClient, admin: Actor) -> None:
    response = client.post(
        "/api/config/divisions", json={"name": "Alpha"}, headers={"x-csrf-token": "forged"}
    )
    assert response.status_code == 403


def test_reads_do_not_require_a_csrf_token(client: TestClient, admin: Actor) -> None:
    project = {"x-project-id": str(admin.project_id)}
    assert client.get("/api/config/divisions", headers=project).status_code == 200


# --------------------------------------------------------------- role matrix


@pytest.mark.parametrize(
    ("role", "expected"),
    [(ProjectRole.ADMIN, 201), (ProjectRole.COLLABORATOR, 201), (ProjectRole.STAFF, 403)],
)
def test_staff_may_not_change_configuration(
    client: TestClient, admin: Actor, session_factory, role: ProjectRole, expected: int
) -> None:
    actor = _member(client, session_factory, admin, role)
    assert actor.post("/api/config/divisions", json={"name": "Alpha"}).status_code == expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [(ProjectRole.ADMIN, 201), (ProjectRole.COLLABORATOR, 201), (ProjectRole.STAFF, 403)],
)
def test_staff_may_not_generate_schedules(
    client: TestClient, admin: Actor, session_factory, role: ProjectRole, expected: int
) -> None:
    actor = _member(client, session_factory, admin, role)
    response = actor.post(
        "/api/schedule/generate",
        json={"start_date": "2026-10-01", "end_date": "2026-10-02"},
    )
    assert response.status_code == expected


def test_a_request_must_name_its_project(client: TestClient, admin: Actor) -> None:
    response = admin.in_project(None).get("/api/config/divisions")
    assert response.status_code == 400
    assert response.json()["code"] == "NO_PROJECT"


def test_staff_cannot_read_other_peoples_time_off(
    client: TestClient, admin: Actor, session_factory
) -> None:
    """Scoping happens in the query, so supplying another id changes nothing."""
    division = admin.post("/api/config/divisions", json={"name": "Alpha"}).json()
    alice = admin.post(
        "/api/config/people",
        json={"full_name": "Alice", "division_id": division["id"], "working_weekdays": [0, 1]},
    ).json()
    bob = admin.post(
        "/api/config/people",
        json={"full_name": "Bob", "division_id": division["id"], "working_weekdays": [0, 1]},
    ).json()

    admin.post(
        "/api/time-off",
        json={"person_id": bob["id"], "start_date": "2026-10-01", "end_date": "2026-10-02"},
    )

    staff = _member(client, session_factory, admin, ProjectRole.STAFF, alice["id"])

    # Even asking for Bob's id explicitly returns only Alice's own records.
    assert staff.get(f"/api/time-off?person_id={bob['id']}").json() == []


def test_staff_cannot_request_time_off_for_someone_else(
    client: TestClient, admin: Actor, session_factory
) -> None:
    division = admin.post("/api/config/divisions", json={"name": "Alpha"}).json()
    alice = admin.post(
        "/api/config/people",
        json={"full_name": "Alice", "division_id": division["id"], "working_weekdays": [0]},
    ).json()
    bob = admin.post(
        "/api/config/people",
        json={"full_name": "Bob", "division_id": division["id"], "working_weekdays": [0]},
    ).json()

    staff = _member(client, session_factory, admin, ProjectRole.STAFF, alice["id"])

    response = staff.post(
        "/api/time-off",
        json={"person_id": bob["id"], "start_date": "2026-10-01", "end_date": "2026-10-02"},
    )
    assert response.status_code == 403


# ------------------------------------------------------------ wizard progress


def test_finishing_the_wizard_is_remembered(client: TestClient, admin: Actor) -> None:
    """Otherwise every reload sends the administrator back through setup."""
    assert admin.get("/api/config/settings").json()["setup_completed"] is False
    assert admin.post("/api/setup/complete").status_code == 200
    assert admin.get("/api/config/settings").json()["setup_completed"] is True


def test_staff_may_not_mark_the_wizard_finished(
    client: TestClient, admin: Actor, session_factory
) -> None:
    staff = _member(client, session_factory, admin, ProjectRole.STAFF)
    assert staff.post("/api/setup/complete").status_code == 403


def test_saving_settings_does_not_reset_wizard_completion(client: TestClient, admin: Actor) -> None:
    admin.post("/api/setup/complete")
    admin.put("/api/config/settings", json={"rest_period_hours": 10})
    assert admin.get("/api/config/settings").json()["setup_completed"] is True
