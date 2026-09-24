"""Properties that matter once the server is reachable from the internet."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shabetz.api.deps import settings_dep
from shabetz.config import Settings
from tests.integration.conftest import ADMIN_PASSWORD

SETUP_CODE = "ABCD-EFGH-JKLM"


def _client_with(app: FastAPI, settings: Settings, **overrides: object) -> Iterator[TestClient]:
    configured = settings.model_copy(update=overrides)
    app.dependency_overrides[settings_dep] = lambda: configured
    with TestClient(app) as client:
        yield client


@pytest.fixture
def hardened(app: FastAPI, settings: Settings) -> Iterator[TestClient]:
    """Realistic limits: per-address throttle below the account lockout."""
    yield from _client_with(app, settings, login_ip_max_failures=5, login_max_attempts=50)


def _bootstrap(client: TestClient, **extra: object) -> None:
    response = client.post(
        "/api/setup/bootstrap-admin",
        json={
            "email": "admin@example.com",
            "full_name": "Admin",
            "password": ADMIN_PASSWORD,
            **extra,
        },
    )
    assert response.status_code == 201, response.text


# ------------------------------------------------------------- lockout abuse


def test_an_attacker_is_throttled_before_the_account_locks(hardened: TestClient) -> None:
    _bootstrap(hardened)
    hardened.cookies.clear()

    statuses = [
        hardened.post(
            "/api/auth/login", json={"email": "admin@example.com", "password": "guess"}
        ).status_code
        for _ in range(8)
    ]
    assert statuses[:5] == [401] * 5
    assert set(statuses[5:]) == {429}, "the attacking address must be throttled"


def test_throttled_guesses_do_not_count_against_the_account(
    app: FastAPI, settings: Settings, session_factory
) -> None:
    """The real owner must still be able to sign in once the attacker is blocked."""
    from shabetz.db.models import User

    configured = settings.model_copy(update={"login_ip_max_failures": 5, "login_max_attempts": 50})
    app.dependency_overrides[settings_dep] = lambda: configured

    with TestClient(app) as attacker:
        _bootstrap(attacker)
        attacker.cookies.clear()
        for _ in range(40):
            attacker.post(
                "/api/auth/login", json={"email": "admin@example.com", "password": "guess"}
            )

    with session_factory() as db:
        admin = db.query(User).filter_by(email="admin@example.com").one()
        # Only the five that got through reached the account's counter.
        assert admin.failed_login_count == 5
        assert admin.locked_until is None


def test_throttle_returns_retry_after(hardened: TestClient) -> None:
    _bootstrap(hardened)
    hardened.cookies.clear()
    for _ in range(5):
        hardened.post("/api/auth/login", json={"email": "admin@example.com", "password": "x"})
    blocked = hardened.post("/api/auth/login", json={"email": "admin@example.com", "password": "x"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_signing_in_to_your_own_account_does_not_clear_the_record(
    app: FastAPI, settings: Settings
) -> None:
    """Otherwise an attacker with any valid account could reset between guesses."""
    configured = settings.model_copy(update={"login_ip_max_failures": 3})
    app.dependency_overrides[settings_dep] = lambda: configured

    with TestClient(app) as client:
        _bootstrap(client)
        client.cookies.clear()
        for _ in range(2):
            client.post("/api/auth/login", json={"email": "admin@example.com", "password": "x"})
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
            ).status_code
            == 200
        )
        client.post("/api/auth/login", json={"email": "admin@example.com", "password": "x"})
        assert (
            client.post(
                "/api/auth/login", json={"email": "admin@example.com", "password": "x"}
            ).status_code
            == 429
        )


# --------------------------------------------------------------- setup code


def test_server_requires_the_setup_code(app: FastAPI, settings: Settings) -> None:
    """Otherwise a fresh deployment belongs to whoever loads it first."""
    for client in _client_with(app, settings, setup_token=SETUP_CODE):
        caps = client.get("/api/meta/capabilities").json()
        assert caps["setup_code_required"] is True

        missing = client.post(
            "/api/setup/bootstrap-admin",
            json={"email": "a@b.c", "full_name": "A", "password": ADMIN_PASSWORD},
        )
        assert missing.status_code == 403

        wrong = client.post(
            "/api/setup/bootstrap-admin",
            json={
                "email": "a@b.c",
                "full_name": "A",
                "password": ADMIN_PASSWORD,
                "setup_code": "WRONG-CODE-0000",
            },
        )
        assert wrong.status_code == 403
        assert client.get("/api/meta/capabilities").json()["setup_complete"] is False

        _bootstrap(client, setup_code=SETUP_CODE)
        assert client.get("/api/meta/capabilities").json()["setup_complete"] is True


def test_setup_code_is_forgiving_about_case_and_spacing(app: FastAPI, settings: Settings) -> None:
    """It is read from a log and typed by a person."""
    for client in _client_with(app, settings, setup_token=SETUP_CODE):
        _bootstrap(client, setup_code="  abcd-efgh-jklm ")


def test_production_server_without_a_code_fails_closed(app: FastAPI, settings: Settings) -> None:
    """A misconfigured server must refuse, not fall back to letting anyone in."""
    for client in _client_with(
        app, settings, environment="prod", deployment="server", setup_token=""
    ):
        response = client.post(
            "/api/setup/bootstrap-admin",
            json={"email": "a@b.c", "full_name": "A", "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 503
        assert "shabetz serve" in response.json()["detail"]


def test_desktop_does_not_ask_for_a_setup_code(app: FastAPI, settings: Settings) -> None:
    """It listens only on the local machine, so there is nobody to race."""
    for client in _client_with(app, settings, environment="prod", deployment="desktop"):
        assert client.get("/api/meta/capabilities").json()["setup_code_required"] is False
        _bootstrap(client)


def test_guessing_the_setup_code_is_throttled(app: FastAPI, settings: Settings) -> None:
    for client in _client_with(app, settings, setup_token=SETUP_CODE, login_ip_max_failures=3):
        codes = [
            client.post(
                "/api/setup/bootstrap-admin",
                json={
                    "email": "a@b.c",
                    "full_name": "A",
                    "password": ADMIN_PASSWORD,
                    "setup_code": f"GUESS-{n:04d}-XXXX",
                },
            ).status_code
            for n in range(5)
        ]
        assert codes[:3] == [403, 403, 403]
        assert codes[3:] == [429, 429]


# ------------------------------------------------------------ static frontend


def test_unknown_api_routes_stay_json_404s(client: TestClient) -> None:
    """The frontend catch-all must never answer for the API."""
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
