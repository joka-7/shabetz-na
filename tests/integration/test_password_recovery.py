"""Getting back in to the desktop app after forgetting the password.

The desktop app usually has a single administrator and nobody to reset it
for them, so a reset code is written into the app's own folder. These pin that
it works, that it cannot be guessed or reused, and that a hosted server never
offers it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shabetz.auth.recovery import CODE_FILE, RecoveryCodes
from shabetz.config import Settings
from tests.integration.conftest import ADMIN_PASSWORD, Actor

NEW_PASSWORD = "a-brand-new-long-password"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        deployment="desktop",
        data_dir=str(tmp_path),
        secret_key="test-secret-key",
        database_url="sqlite://",
        cookie_secure=False,
        login_max_attempts=3,
        login_ip_max_failures=1000,
    )


def _code_from_file(directory: Path) -> str:
    text = (directory / CODE_FILE).read_text(encoding="utf-8-sig")
    return text.split("\n")[2].strip()


def _reset(client: TestClient, code: str, password: str = NEW_PASSWORD, email: str | None = None):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/auth/recovery/complete",
        json={"email": email or "admin@example.com", "code": code, "password": password},
    )


def test_forgotten_password_is_reset_with_the_code_from_the_file(
    client: TestClient, admin: Actor, tmp_path: Path
) -> None:
    client.cookies.clear()
    assert client.get("/api/meta/capabilities").json()["password_recovery"] is True

    started = client.post("/api/auth/recovery/start")
    assert started.status_code == 200, started.text
    assert (tmp_path / CODE_FILE).exists()
    text = (tmp_path / CODE_FILE).read_text(encoding="utf-8-sig")
    # The file names the administrator, since a forgotten email is common too.
    assert "admin@example.com" in text

    response = _reset(client, _code_from_file(tmp_path).lower())
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "admin@example.com"
    assert not (tmp_path / CODE_FILE).exists()

    client.cookies.clear()
    old = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": ADMIN_PASSWORD}
    )
    assert old.status_code == 401
    new = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": NEW_PASSWORD}
    )
    assert new.status_code == 200


def test_reset_unlocks_a_locked_account(client: TestClient, admin: Actor, tmp_path: Path) -> None:
    client.cookies.clear()
    for _ in range(3):
        client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    locked = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": ADMIN_PASSWORD}
    )
    assert locked.status_code == 403

    client.post("/api/auth/recovery/start")
    assert _reset(client, _code_from_file(tmp_path)).status_code == 200


def test_a_code_works_once(client: TestClient, admin: Actor, tmp_path: Path) -> None:
    client.post("/api/auth/recovery/start")
    code = _code_from_file(tmp_path)
    assert _reset(client, code).status_code == 200
    assert _reset(client, code, password="yet-another-long-password").status_code == 403


def test_a_short_password_does_not_spend_the_code(
    client: TestClient, admin: Actor, tmp_path: Path
) -> None:
    client.post("/api/auth/recovery/start")
    code = _code_from_file(tmp_path)
    assert _reset(client, code, password="short").status_code == 422
    assert _reset(client, code).status_code == 200


def test_an_unknown_email_does_not_spend_the_code(
    client: TestClient, admin: Actor, tmp_path: Path
) -> None:
    client.post("/api/auth/recovery/start")
    code = _code_from_file(tmp_path)
    assert _reset(client, code, email="nobody@example.com").status_code == 422
    assert _reset(client, code).status_code == 200


def test_wrong_guesses_burn_the_code() -> None:
    codes = RecoveryCodes(max_attempts=5)
    code = codes.issue()
    for _ in range(5):
        assert codes.redeem("AAAA-AAAA-AAAA") is False
    assert codes.redeem(code) is False


def test_codes_expire() -> None:
    now = [0.0]
    codes = RecoveryCodes(ttl_seconds=900, clock=lambda: now[0])
    code = codes.issue()
    now[0] = 901
    assert codes.redeem(code) is False


def test_a_new_code_replaces_the_old_one() -> None:
    codes = RecoveryCodes()
    first = codes.issue()
    second = codes.issue()
    assert codes.redeem(first) is False
    assert codes.redeem(second) is True


def test_a_hosted_server_never_offers_it(app, admin: Actor, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    from shabetz.api.deps import settings_dep

    server = settings.model_copy(update={"deployment": "server"})
    app.dependency_overrides[settings_dep] = lambda: server
    assert admin.get("/api/meta/capabilities").json()["password_recovery"] is False
    assert admin.post("/api/auth/recovery/start").status_code == 404
    assert _reset(admin.client, "AAAA-AAAA-AAAA").status_code == 404
