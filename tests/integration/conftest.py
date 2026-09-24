"""API test harness.

These exercise authentication, authorization and request flow, which are
dialect-independent.  The MySQL-specific schema guarantees (utf8mb4, bounded
index keys, DATETIME(6), LONGBLOB) are verified separately in
``tests/unit/test_mysql_schema.py`` by rendering DDL through the MySQL dialect,
and end-to-end against a live server when one is configured.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from shabetz.api.deps import get_db, settings_dep
from shabetz.api.main import create_app
from shabetz.auth.service import create_user
from shabetz.config import Settings
from shabetz.db.models import Base, ProjectMember
from shabetz.domain.enums import ProjectRole


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


# Set to run the same tests against a real server database, e.g. the
# PostgreSQL a hosted deployment uses. Each test creates and drops the schema.
TEST_DATABASE_URL = os.environ.get("SHABETZ_TEST_DATABASE_URL", "")


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    if TEST_DATABASE_URL:
        engine = create_engine(Settings(database_url=TEST_DATABASE_URL).database_url)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        # As the app configures it: otherwise ON DELETE CASCADE does nothing.
        event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.drop_all(engine)
    engine.dispose()


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
    """A signed-in client that carries its CSRF token and project automatically."""

    def __init__(
        self, client: TestClient, csrf: str, user: dict, project_id: int | None = None
    ) -> None:
        self.client = client
        self.csrf = csrf
        self.user = user
        self.project_id = project_id

    def _headers(self, extra: dict | None = None, *, write: bool = True) -> dict:
        headers: dict = {}
        if write:
            headers["x-csrf-token"] = self.csrf
        if self.project_id is not None:
            headers["x-project-id"] = str(self.project_id)
        return {**headers, **(extra or {})}

    def in_project(self, project_id: int | None) -> Actor:
        return Actor(self.client, self.csrf, self.user, project_id)

    def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.get(
            url, headers=self._headers(kw.pop("headers", None), write=False), **kw
        )

    def post(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.post(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def put(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.put(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def delete(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)


ADMIN_PASSWORD = "an-adequately-long-password"


def only_project(client: TestClient) -> int | None:
    projects = client.get("/api/projects").json()
    return projects[0]["id"] if len(projects) == 1 else None


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
    return Actor(client, body["csrf_token"], body["user"], only_project(client))


def make_account(factory: sessionmaker[Session], email: str) -> int:
    """An account with a password and no projects."""
    with factory() as db:
        user = create_user(db, email=email, full_name=email, password=ADMIN_PASSWORD)
        db.commit()
        return user.id


def make_member(
    factory: sessionmaker[Session],
    project_id: int,
    email: str,
    role: ProjectRole,
    person_id: int | None = None,
) -> None:
    """An account with a password, already a member of the project."""
    user_id = make_account(factory, email)
    with factory() as db:
        db.add(
            ProjectMember(project_id=project_id, user_id=user_id, role=role, person_id=person_id)
        )
        db.commit()


def sign_in(client: TestClient, email: str, project_id: int | None = None) -> Actor:
    """Sign in on this client, replacing whoever was signed in on it."""
    client.cookies.clear()
    response = client.post("/api/auth/login", json={"email": email, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    return Actor(client, body["csrf_token"], body["user"], project_id)
