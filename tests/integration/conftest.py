"""API test harness.

These exercise authentication, authorization and request flow, which are
dialect-independent.  The MySQL-specific schema guarantees (utf8mb4, bounded
index keys, DATETIME(6), LONGBLOB) are verified separately in
``tests/unit/test_mysql_schema.py`` by rendering DDL through the MySQL dialect,
and end-to-end against a live server when one is configured.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from shabetz.api.deps import get_db, settings_dep
from shabetz.api.main import create_app
from shabetz.config import Settings
from shabetz.db.models import Base


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        secret_key="test-secret-key",
        database_url="sqlite://",
        cookie_secure=False,
        # Pinned rather than inherited: the lockout tests exercise account
        # lockout in isolation, so the address throttle is set well out of the
        # way. Throttle behaviour has its own tests with realistic values.
        login_max_attempts=8,
        login_ip_max_failures=1000,
    )


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.drop_all(engine)


@pytest.fixture
def app(settings: Settings, session_factory: sessionmaker[Session]) -> FastAPI:
    application = create_app()

    def _get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    application.dependency_overrides[get_db] = _get_db
    application.dependency_overrides[settings_dep] = lambda: settings
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


class Actor:
    """A signed-in client that carries its CSRF token automatically."""

    def __init__(self, client: TestClient, csrf: str, user: dict) -> None:
        self.client = client
        self.csrf = csrf
        self.user = user

    def _headers(self, extra: dict | None = None) -> dict:
        return {"x-csrf-token": self.csrf, **(extra or {})}

    def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.get(url, **kw)

    def post(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.post(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def put(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.put(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def delete(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)


ADMIN_PASSWORD = "an-adequately-long-password"


@pytest.fixture
def admin(client: TestClient) -> Actor:
    response = client.post(
        "/api/setup/bootstrap-admin",
        json={
            "email": "admin@example.com",
            "full_name": "First Admin",
            "password": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return Actor(client, body["csrf_token"], body["user"])
