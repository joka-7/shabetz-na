"""Authentication, the bootstrap window, CSRF, and per-role authorization."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from shabetz.auth.service import create_user
from shabetz.domain.enums import UserRole
from tests.integration.conftest import ADMIN_PASSWORD, Actor


def _sign_in(client: TestClient, email: str, password: str) -> Actor:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    return Actor(client, body["csrf_token"], body["user"])


def _make_user(
    factory: sessionmaker[Session], email: str, role: UserRole, person_id: int | None = None
) -> None:
    with factory() as db:
        create_user(
            db,
            email=email,
            full_name=email,
            role=role,
            password=ADMIN_PASSWORD,
            person_id=person_id,
        )
        db.commit()


# ------------------------------------------------------------ bootstrap window


def test_setup_status_flips_after_first_admin(client: TestClient) -> None:
    assert client.get("/api/setup/status").json()["setup_complete"] is False
    client.post(
        "/api/setup/bootstrap-admin",
        json={"email": "a@example.com", "full_name": "A", "password": ADMIN_PASSWORD},
    )
    assert client.get("/api/setup/status").json()["setup_complete"] is True


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
    client.cookies.clear()
    actor = _sign_in(client, "admin@example.com", ADMIN_PASSWORD)
    assert actor.user["role"] == "ADMIN"
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
    assert client.get("/api/config/divisions").status_code == 200


# --------------------------------------------------------------- role matrix


@pytest.mark.parametrize(
    ("role", "expected"),
    [(UserRole.ADMIN, 201), (UserRole.SCHEDULER, 403), (UserRole.STAFF, 403)],
)
def test_only_admins_may_change_configuration(
    client: TestClient, admin: Actor, session_factory, role: UserRole, expected: int
) -> None:
    if role is not UserRole.ADMIN:
        _make_user(session_factory, f"{role.value.lower()}@example.com", role)
        client.cookies.clear()
        actor = _sign_in(client, f"{role.value.lower()}@example.com", ADMIN_PASSWORD)
    else:
        actor = admin
    assert actor.post("/api/config/divisions", json={"name": "Alpha"}).status_code == expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [(UserRole.ADMIN, 201), (UserRole.SCHEDULER, 201), (UserRole.STAFF, 403)],
)
def test_staff_may_not_generate_schedules(
    client: TestClient, admin: Actor, session_factory, role: UserRole, expected: int
) -> None:
    if role is not UserRole.ADMIN:
        _make_user(session_factory, f"{role.value.lower()}@example.com", role)
        client.cookies.clear()
        actor = _sign_in(client, f"{role.value.lower()}@example.com", ADMIN_PASSWORD)
    else:
        actor = admin
    response = actor.post(
        "/api/schedule/generate",
        json={"start_date": "2026-10-01", "end_date": "2026-10-02"},
    )
    assert response.status_code == expected


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

    _make_user(session_factory, "alice@example.com", UserRole.STAFF, person_id=alice["id"])
    client.cookies.clear()
    staff = _sign_in(client, "alice@example.com", ADMIN_PASSWORD)

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

    _make_user(session_factory, "alice@example.com", UserRole.STAFF, person_id=alice["id"])
    client.cookies.clear()
    staff = _sign_in(client, "alice@example.com", ADMIN_PASSWORD)

    response = staff.post(
        "/api/time-off",
        json={"person_id": bob["id"], "start_date": "2026-10-01", "end_date": "2026-10-02"},
    )
    assert response.status_code == 403


# ------------------------------------------------------------- Google sign-in


def test_google_routes_are_absent_when_unconfigured(client: TestClient) -> None:
    """No credentials means the feature does not exist, not that it is broken."""
    assert client.get("/api/meta/capabilities").json()["google_enabled"] is False
    assert client.get("/api/auth/google/authorize", follow_redirects=False).status_code == 404
    assert (
        client.get("/api/auth/google/callback?code=x&state=y", follow_redirects=False).status_code
        == 404
    )


def test_google_authorize_redirects_and_sets_a_state_cookie(app, settings, session_factory) -> None:
    """With credentials present the flow starts at Google, guarded by state."""
    from urllib.parse import parse_qs, urlparse

    from shabetz.api.deps import settings_dep

    configured = settings.model_copy(
        update={
            "google_client_id": "client-id.apps.googleusercontent.com",
            "google_client_secret": "client-secret",
        }
    )
    app.dependency_overrides[settings_dep] = lambda: configured

    with TestClient(app) as configured_client:
        assert configured_client.get("/api/meta/capabilities").json()["google_enabled"] is True

        response = configured_client.get("/api/auth/google/authorize", follow_redirects=False)
        assert response.status_code == 307

        location = urlparse(response.headers["location"])
        assert location.netloc == "accounts.google.com"
        query = parse_qs(location.query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["state"][0]

        # The cookie carrying state must not be readable by scripts.
        cookie_header = response.headers["set-cookie"]
        assert "shabetz_oauth_state=" in cookie_header
        assert "httponly" in cookie_header.lower()


def test_google_callback_without_state_returns_to_login_with_a_reason(app, settings) -> None:
    from shabetz.api.deps import settings_dep

    configured = settings.model_copy(
        update={
            "google_client_id": "client-id",
            "google_client_secret": "client-secret",
        }
    )
    app.dependency_overrides[settings_dep] = lambda: configured

    with TestClient(app) as configured_client:
        response = configured_client.get(
            "/api/auth/google/callback?code=some-code&state=unmatched",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/?auth_error=failed"


def test_google_callback_reports_cancellation(app, settings) -> None:
    from shabetz.api.deps import settings_dep

    configured = settings.model_copy(update={"google_client_id": "c", "google_client_secret": "s"})
    app.dependency_overrides[settings_dep] = lambda: configured

    with TestClient(app) as configured_client:
        response = configured_client.get(
            "/api/auth/google/callback?error=access_denied", follow_redirects=False
        )
        assert response.headers["location"] == "/?auth_error=cancelled"


# ------------------------------------------------------------ wizard progress


def test_finishing_the_wizard_is_remembered(client: TestClient, admin: Actor) -> None:
    """Otherwise every reload sends the administrator back through setup."""
    assert client.get("/api/setup/status").json()["wizard_completed"] is False
    assert admin.post("/api/setup/complete").status_code == 200
    assert client.get("/api/setup/status").json()["wizard_completed"] is True
    assert admin.get("/api/config/settings").json()["setup_completed"] is True


def test_only_admins_may_mark_the_wizard_finished(
    client: TestClient, admin: Actor, session_factory
) -> None:
    _make_user(session_factory, "sched@example.com", UserRole.SCHEDULER)
    client.cookies.clear()
    scheduler = _sign_in(client, "sched@example.com", ADMIN_PASSWORD)
    assert scheduler.post("/api/setup/complete").status_code == 403


def test_saving_settings_does_not_reset_wizard_completion(client: TestClient, admin: Actor) -> None:
    admin.post("/api/setup/complete")
    admin.put("/api/config/settings", json={"rest_period_hours": 10})
    assert admin.get("/api/config/settings").json()["setup_completed"] is True
