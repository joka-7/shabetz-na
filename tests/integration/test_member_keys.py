"""End-to-end encryption keys: each account stores and fetches only its own.

The server must keep exactly what the browser uploads and refuse anything that
is not the right size, because a wrapped key it accepted but no device can
open is a lost key (docs/E2EE-DESIGN.md §2, §4.1).
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from shabetz.db.models import MemberKey
from tests.integration.conftest import Actor, make_account, sign_in


def _b64(size: int, fill: int) -> str:
    """libsodium's default encoding (URL-safe, unpadded) of ``size`` bytes of ``fill``."""
    return base64.urlsafe_b64encode(bytes([fill]) * size).rstrip(b"=").decode()


def _key(fill: int = 1) -> dict:
    return {
        "public_key": _b64(32, fill),
        "wrapped_sk_passphrase": _b64(72, fill + 1),
        "wrapped_sk_recovery": _b64(72, fill + 2),
        "kdf_salt": _b64(16, fill + 3),
        "kdf_opslimit": 3,
        "kdf_memlimit": 64 * 1024 * 1024,
    }


def _stored(response_json: dict) -> dict:
    return {field: response_json[field] for field in _key()}


def test_create_then_fetch_returns_what_was_uploaded(admin: Actor) -> None:
    # Arrange
    body = _key()

    # Act
    created = admin.post("/api/keys/me", json=body)
    fetched = admin.get("/api/keys/me")

    # Assert
    assert created.status_code == 201, created.text
    assert fetched.status_code == 200
    assert _stored(fetched.json()) == body


def test_fetch_before_setup_is_not_found(admin: Actor) -> None:
    assert admin.get("/api/keys/me").status_code == 404


def test_a_second_key_pair_is_refused(admin: Actor) -> None:
    # Arrange
    admin.post("/api/keys/me", json=_key(1))

    # Act
    second = admin.post("/api/keys/me", json=_key(9))

    # Assert
    assert second.status_code == 409
    assert _stored(admin.get("/api/keys/me").json()) == _key(1)


def test_rewrap_replaces_the_wraps_and_keeps_the_public_key(admin: Actor) -> None:
    # Arrange
    admin.post("/api/keys/me", json=_key(1))
    new_wraps = {k: v for k, v in _key(20).items() if k != "public_key"}

    # Act
    response = admin.put("/api/keys/me/wraps", json=new_wraps)

    # Assert
    assert response.status_code == 200, response.text
    assert _stored(response.json()) == {**new_wraps, "public_key": _key(1)["public_key"]}


def test_rewrap_keeps_the_replaced_wraps(admin: Actor, session_factory) -> None:  # type: ignore[no-untyped-def]
    # Arrange
    original = _key(1)
    admin.post("/api/keys/me", json=original)
    new_wraps = {k: v for k, v in _key(20).items() if k != "public_key"}

    # Act
    admin.put("/api/keys/me/wraps", json=new_wraps)

    # Assert
    with session_factory() as db:
        stored = db.get(MemberKey, admin.user["id"])
        assert stored is not None
        assert stored.previous_wraps == {k: v for k, v in original.items() if k != "public_key"}


def test_rewrap_without_a_key_is_not_found(admin: Actor) -> None:
    wraps = {k: v for k, v in _key().items() if k != "public_key"}
    assert admin.put("/api/keys/me/wraps", json=wraps).status_code == 404


def test_each_account_sees_only_its_own_key(
    client: TestClient,
    admin: Actor,
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    # Arrange
    admin.post("/api/keys/me", json=_key(1))
    make_account(session_factory, "other@example.com")
    other = sign_in(TestClient(client.app), "other@example.com")

    # Act
    response = other.get("/api/keys/me")

    # Assert
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("public_key", _b64(31, 1)),
        ("public_key", _b64(32, 1) + "=="),
        ("public_key", "not base64 !!"),
        ("public_key", _b64(32, 1).replace("A", "+", 1)),
        ("public_key", _b64(32, 1)[:20] + "!!" + _b64(32, 1)[22:]),
        ("public_key", _b64(32, 1)[:-1] + "B"),
        ("public_key", _b64(32, 1) + "\n"),
        ("public_key", "A" * 100_000),
        ("wrapped_sk_passphrase", _b64(32, 1)),
        ("wrapped_sk_recovery", _b64(73, 1)),
        ("kdf_salt", _b64(32, 1)),
        ("kdf_opslimit", 1),
        ("kdf_opslimit", 11),
        ("kdf_memlimit", 1024),
        ("kdf_memlimit", 2 * 1024 * 1024 * 1024),
    ],
)
def test_malformed_uploads_are_refused(admin: Actor, field: str, value: object) -> None:
    # Arrange
    body = {**_key(), field: value}

    # Act
    response = admin.post("/api/keys/me", json=body)

    # Assert
    assert response.status_code == 422
    assert admin.get("/api/keys/me").status_code == 404


def test_writes_need_the_csrf_token(admin: Actor) -> None:
    response = admin.client.post("/api/keys/me", json=_key())
    assert response.status_code == 403


def test_signed_out_requests_are_refused(client: TestClient) -> None:
    assert client.get("/api/keys/me").status_code == 401
