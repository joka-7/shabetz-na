"""Signing in -- and up -- with Google through Firebase."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shabetz.api.deps import settings_dep
from shabetz.auth.firebase import FirebaseVerifier
from shabetz.auth.service import bootstrap_first_admin
from shabetz.config import Settings
from tests.integration.conftest import ADMIN_PASSWORD, Actor
from tests.unit.test_firebase_tokens import NOW, PROJECT, claims, make_key, sign

KEY = make_key()


@pytest.fixture
def google(app: FastAPI, settings: Settings) -> Iterator[TestClient]:
    configured = settings.model_copy(
        update={"firebase_api_key": "public-api-key", "firebase_project_id": PROJECT}
    )
    app.dependency_overrides[settings_dep] = lambda: configured
    app.state.firebase_verifier = FirebaseVerifier(
        PROJECT,
        fetch_keys=lambda: ({"keys": [KEY.as_dict(private=False)]}, 3600),
        clock=lambda: NOW,
    )
    with TestClient(app) as client:
        yield client


def _sign_in(client: TestClient, **overrides: Any):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/firebase", json={"id_token": sign(KEY, claims(**overrides))})


def test_capabilities_hand_the_browser_the_firebase_config(google: TestClient) -> None:
    caps = google.get("/api/meta/capabilities").json()
    assert caps["firebase"] == {
        "apiKey": "public-api-key",
        "authDomain": f"{PROJECT}.firebaseapp.com",
        "projectId": PROJECT,
        "appId": "",
    }
    # Nobody claims a Google-sign-in site; everyone signs up for themselves.
    assert caps["setup_complete"] is True


def test_google_sign_in_is_absent_when_not_configured(client: TestClient) -> None:
    assert client.get("/api/meta/capabilities").json()["firebase"] is None
    assert client.post("/api/auth/firebase", json={"id_token": "x"}).status_code == 404


def test_a_new_google_account_signs_up_and_can_start_a_project(google: TestClient) -> None:
    response = _sign_in(google)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "dana@example.com"
    assert google.get("/api/projects").json() == []

    actor = Actor(google, body["csrf_token"], body["user"])
    created = actor.post("/api/projects", json={"name": "Dana's team"})
    assert created.json()["role"] == "ADMIN"


def test_signing_in_again_finds_the_same_account(google: TestClient) -> None:
    first = _sign_in(google).json()["user"]["id"]
    google.cookies.clear()
    assert _sign_in(google, email="dana.new@example.com").json()["user"]["id"] == first


def test_an_existing_password_account_is_linked_by_verified_address(
    google: TestClient, session_factory
) -> None:
    """Someone who set the site up with a password keeps their projects."""
    with session_factory() as db:
        bootstrap_first_admin(
            db, email="dana@example.com", full_name="Dana", password=ADMIN_PASSWORD
        )
        db.commit()

    body = _sign_in(google).json()
    assert body["user"]["email"] == "dana@example.com"
    assert google.get("/api/projects").json()[0]["role"] == "ADMIN"


def test_an_unverified_address_is_refused(google: TestClient) -> None:
    assert _sign_in(google, email_verified=False).status_code == 403


def test_an_invalid_token_is_refused(google: TestClient) -> None:
    assert _sign_in(google, aud="someone-elses-project").status_code == 401
    assert google.get("/api/auth/me").status_code == 401


def test_password_bootstrap_is_shut_when_google_sign_in_is_on(google: TestClient) -> None:
    response = google.post(
        "/api/setup/bootstrap-admin",
        json={"email": "a@example.com", "full_name": "A", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 409
