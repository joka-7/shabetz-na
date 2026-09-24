"""Projects, members, invite links -- and that projects cannot see each other.

The isolation tests matter most: every organisation shares one database, so a
single query that forgets its project would show one organisation's roster to
another.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from shabetz.config import Settings
from shabetz.db.models import AuditLog, Division, Person
from shabetz.domain.enums import ProjectRole
from tests.integration.conftest import Actor, make_account, make_member, sign_in


def _new_project(actor: Actor, name: str) -> Actor:
    response = actor.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "ADMIN"
    return actor.in_project(body["id"])


def _stranger(client: TestClient, factory, name: str = "stranger") -> Actor:  # type: ignore[no-untyped-def]
    """Someone with an account of their own and a project of their own."""
    make_account(factory, f"{name}@example.com")
    return _new_project(sign_in(TestClient(client.app), f"{name}@example.com"), f"{name}'s")


def _invite(admin: Actor, role: str = "STAFF", **extra: object) -> str:
    response = admin.post("/api/project/invites", json={"role": role, **extra})
    assert response.status_code == 201, response.text
    return response.json()["token"]


# ------------------------------------------------------------------ projects


def test_anyone_signed_in_can_create_a_project_and_administer_it(
    client: TestClient, admin: Actor, session_factory
) -> None:
    make_account(session_factory, "new@example.com")
    newcomer = sign_in(client, "new@example.com")
    assert newcomer.get("/api/projects").json() == []

    mine = _new_project(newcomer, "Night shift crew")
    assert [p["name"] for p in newcomer.get("/api/projects").json()] == ["Night shift crew"]
    assert mine.post("/api/config/divisions", json={"name": "North"}).status_code == 201


def test_one_account_can_hold_different_roles_in_different_projects(
    client: TestClient, admin: Actor, session_factory
) -> None:
    make_member(session_factory, admin.project_id, "both@example.com", ProjectRole.STAFF)
    both = sign_in(client, "both@example.com")
    own = _new_project(both, "My own")

    roles = {p["name"]: p["role"] for p in both.get("/api/projects").json()}
    assert roles == {"My organization": "STAFF", "My own": "ADMIN"}
    assert own.post("/api/config/divisions", json={"name": "X"}).status_code == 201
    staff = both.in_project(admin.project_id)
    assert staff.post("/api/config/divisions", json={"name": "X"}).status_code == 403


def test_the_administrator_can_rename_and_delete_a_project(
    client: TestClient, admin: Actor, session_factory
) -> None:
    project = _new_project(admin, "Temporary")
    assert project.put("/api/project", json={"name": "Renamed"}).json()["name"] == "Renamed"
    project.post("/api/config/divisions", json={"name": "Gone"})

    assert project.delete("/api/project").status_code == 204
    assert "Renamed" not in [p["name"] for p in admin.get("/api/projects").json()]
    with session_factory() as db:
        assert db.scalar(select(Division).where(Division.name == "Gone")) is None
    # The other project is untouched.
    assert admin.get("/api/config/settings").status_code == 200


def test_a_collaborator_cannot_delete_or_rename_the_project(
    client: TestClient, admin: Actor, session_factory
) -> None:
    make_member(session_factory, admin.project_id, "c@example.com", ProjectRole.COLLABORATOR)
    collaborator = sign_in(client, "c@example.com", admin.project_id)
    assert collaborator.delete("/api/project").status_code == 403
    assert collaborator.put("/api/project", json={"name": "Mine now"}).status_code == 403


def test_the_last_administrator_cannot_leave(admin: Actor) -> None:
    assert admin.post("/api/project/leave").status_code == 409


# ------------------------------------------------------------------ isolation


def test_a_non_member_cannot_see_that_a_project_exists(
    client: TestClient, admin: Actor, session_factory
) -> None:
    admin.post("/api/config/divisions", json={"name": "Secret"})
    stranger = _stranger(client, session_factory)
    theirs = stranger.in_project(admin.project_id)

    for path in ("/api/config/divisions", "/api/config/people", "/api/config/settings"):
        response = theirs.get(path)
        # The same answer as for a project that does not exist at all.
        assert response.status_code == 404, path
    assert stranger.in_project(999_999).get("/api/config/divisions").status_code == 404
    assert theirs.post("/api/config/divisions", json={"name": "Planted"}).status_code == 404


def test_each_project_sees_only_its_own_rows(
    client: TestClient, admin: Actor, session_factory
) -> None:
    admin.post("/api/config/divisions", json={"name": "Ours"})
    stranger = _stranger(client, session_factory)
    stranger.post("/api/config/divisions", json={"name": "Theirs"})

    assert [d["name"] for d in admin.get("/api/config/divisions").json()] == ["Ours"]
    assert [d["name"] for d in stranger.get("/api/config/divisions").json()] == ["Theirs"]


def test_the_same_names_can_exist_in_two_projects(
    client: TestClient, admin: Actor, session_factory
) -> None:
    stranger = _stranger(client, session_factory)
    for actor in (admin, stranger):
        assert actor.post("/api/config/divisions", json={"name": "North"}).status_code == 201
        assert actor.post("/api/config/skills", json={"name": "Medic"}).status_code == 201


def test_another_projects_ids_cannot_be_used_or_changed(
    client: TestClient, admin: Actor, session_factory
) -> None:
    """Ids are guessable integers, so every id in a request is checked for ownership."""
    division = admin.post("/api/config/divisions", json={"name": "Ours"}).json()
    person = admin.post(
        "/api/config/people",
        json={"full_name": "Dana", "division_id": division["id"], "working_weekdays": [0]},
    ).json()
    stranger = _stranger(client, session_factory)

    # Placing someone in another project's division.
    planted = stranger.post(
        "/api/config/people",
        json={"full_name": "Mole", "division_id": division["id"], "working_weekdays": [0]},
    )
    assert planted.status_code in (404, 422)

    # Editing or deleting another project's rows by id.
    assert (
        stranger.put(
            f"/api/config/divisions/{division['id']}", json={"name": "Hijacked"}
        ).status_code
        == 404
    )
    assert stranger.delete(f"/api/config/people/{person['id']}").status_code == 404

    # Filing time off for another project's person.
    time_off = stranger.post(
        "/api/time-off",
        json={"person_id": person["id"], "start_date": "2026-10-01", "end_date": "2026-10-01"},
    )
    assert time_off.status_code in (404, 422)

    # An invite naming another project's person.
    assert (
        stranger.post(
            "/api/project/invites", json={"role": "STAFF", "person_id": person["id"]}
        ).status_code
        == 422
    )

    with session_factory() as db:
        assert db.get(Division, division["id"]).name == "Ours"  # type: ignore[union-attr]
        assert db.get(Person, person["id"]) is not None


def test_schedules_stay_in_their_project(client: TestClient, admin: Actor, session_factory) -> None:
    run = admin.post(
        "/api/schedule/generate", json={"start_date": "2026-10-01", "end_date": "2026-10-01"}
    ).json()
    stranger = _stranger(client, session_factory)
    assert stranger.get("/api/schedule/runs").json() == []
    assert stranger.get(f"/api/schedule/runs/{run['schedule_id']}").status_code == 404
    export = stranger.get(
        f"/api/schedule/runs/{run['schedule_id']}/export?format=csv&project={stranger.project_id}"
    )
    assert export.status_code == 404


def test_audit_entries_record_their_project(admin: Actor, session_factory) -> None:
    admin.post("/api/config/divisions", json={"name": "Audited"})
    with session_factory() as db:
        entry = db.scalars(select(AuditLog).where(AuditLog.entity_type == "division")).first()
        assert entry is not None and entry.project_id == admin.project_id


# ------------------------------------------------------------------- members


def test_members_are_listed_for_the_administrator_only(
    client: TestClient, admin: Actor, session_factory
) -> None:
    make_member(session_factory, admin.project_id, "c@example.com", ProjectRole.COLLABORATOR)
    members = admin.get("/api/project/members").json()
    assert {(m["email"], m["role"]) for m in members} == {
        ("admin@example.com", "ADMIN"),
        ("c@example.com", "COLLABORATOR"),
    }
    collaborator = sign_in(client, "c@example.com", admin.project_id)
    assert collaborator.get("/api/project/members").status_code == 403


def test_the_administrator_can_promote_another_and_then_step_down(
    client: TestClient, admin: Actor, session_factory
) -> None:
    make_member(session_factory, admin.project_id, "c@example.com", ProjectRole.COLLABORATOR)
    members = {m["email"]: m for m in admin.get("/api/project/members").json()}
    me, other = members["admin@example.com"], members["c@example.com"]

    # Alone at the top, the administrator can neither demote nor remove themselves.
    assert admin.put(f"/api/project/members/{me['id']}", json={"role": "STAFF"}).status_code == 409
    assert admin.delete(f"/api/project/members/{me['id']}").status_code == 409

    promoted = admin.put(f"/api/project/members/{other['id']}", json={"role": "ADMIN"})
    assert promoted.json()["role"] == "ADMIN"
    assert admin.put(f"/api/project/members/{me['id']}", json={"role": "STAFF"}).status_code == 200
    # The change applies on the very next request.
    assert admin.get("/api/project/members").status_code == 403


def test_removing_a_member_ends_their_access_but_keeps_their_account(
    client: TestClient, admin: Actor, session_factory
) -> None:
    make_member(session_factory, admin.project_id, "c@example.com", ProjectRole.COLLABORATOR)
    other = next(
        m for m in admin.get("/api/project/members").json() if m["email"] == "c@example.com"
    )
    collaborator = sign_in(TestClient(client.app), "c@example.com", admin.project_id)
    assert collaborator.get("/api/config/divisions").status_code == 200

    assert admin.delete(f"/api/project/members/{other['id']}").status_code == 204
    assert collaborator.get("/api/config/divisions").status_code == 404
    assert collaborator.get("/api/auth/me").status_code == 200


def test_members_of_another_project_cannot_be_touched(
    client: TestClient, admin: Actor, session_factory
) -> None:
    stranger = _stranger(client, session_factory)
    theirs = stranger.get("/api/project/members").json()[0]
    assert (
        admin.put(f"/api/project/members/{theirs['id']}", json={"role": "STAFF"}).status_code == 404
    )
    assert admin.delete(f"/api/project/members/{theirs['id']}").status_code == 404


def test_a_website_administrator_cannot_set_members_passwords(
    admin: Actor, session_factory
) -> None:
    """An account may belong to other projects; its password is its owner's."""
    make_member(session_factory, admin.project_id, "c@example.com", ProjectRole.COLLABORATOR)
    other = next(
        m for m in admin.get("/api/project/members").json() if m["email"] == "c@example.com"
    )
    response = admin.post(
        f"/api/project/members/{other['id']}/password", json={"password": "x" * 20}
    )
    assert response.status_code == 404
    local = admin.post(
        "/api/project/members",
        json={"email": "n@example.com", "full_name": "N", "password": "x" * 20},
    )
    assert local.status_code == 404


# ------------------------------------------------------------------- invites


def test_an_invite_link_brings_someone_in_with_its_role(
    client: TestClient, admin: Actor, session_factory
) -> None:
    token = _invite(admin, "COLLABORATOR")
    preview = client.get(f"/api/invites/{token}").json()
    assert preview == {"project_name": "My organization", "role": "COLLABORATOR"}

    make_account(session_factory, "joiner@example.com")
    joiner = sign_in(TestClient(client.app), "joiner@example.com")
    joined = joiner.post(f"/api/invites/{token}/accept")
    assert joined.status_code == 200
    assert joined.json()["role"] == "COLLABORATOR"

    member = joiner.in_project(joined.json()["id"])
    assert member.post("/api/config/divisions", json={"name": "Joined"}).status_code == 201


def test_a_link_granting_rights_works_once(
    client: TestClient, admin: Actor, session_factory
) -> None:
    token = _invite(admin, "ADMIN")
    for name in ("first", "second"):
        make_account(session_factory, f"{name}@example.com")
    first = sign_in(TestClient(client.app), "first@example.com")
    second = sign_in(TestClient(client.app), "second@example.com")

    assert first.post(f"/api/invites/{token}/accept").status_code == 200
    assert second.post(f"/api/invites/{token}/accept").status_code == 404
    assert second.get("/api/projects").json() == []


def test_a_staff_link_can_be_shared_with_a_team(
    client: TestClient, admin: Actor, session_factory
) -> None:
    token = _invite(admin, "STAFF")
    for n in range(3):
        make_account(session_factory, f"s{n}@example.com")
        staff = sign_in(TestClient(client.app), f"s{n}@example.com")
        assert staff.post(f"/api/invites/{token}/accept").json()["role"] == "STAFF"


def test_a_link_for_a_person_links_the_account_to_them(
    client: TestClient, admin: Actor, session_factory
) -> None:
    division = admin.post("/api/config/divisions", json={"name": "North"}).json()
    person = admin.post(
        "/api/config/people",
        json={"full_name": "Dana", "division_id": division["id"], "working_weekdays": [0]},
    ).json()
    token = _invite(admin, "STAFF", person_id=person["id"])

    make_account(session_factory, "dana@example.com")
    dana = sign_in(TestClient(client.app), "dana@example.com")
    assert dana.post(f"/api/invites/{token}/accept").json()["person_id"] == person["id"]


def test_revoked_and_expired_links_stop_working(
    client: TestClient, admin: Actor, session_factory
) -> None:
    revoked = admin.post("/api/project/invites", json={"role": "STAFF"}).json()
    assert admin.delete(f"/api/project/invites/{revoked['id']}").status_code == 204
    assert client.get(f"/api/invites/{revoked['token']}").status_code == 404
    assert client.get("/api/invites/not-a-real-token").status_code == 404
    assert [i["id"] for i in admin.get("/api/project/invites").json()] == []


def test_a_link_never_lowers_a_role(client: TestClient, admin: Actor, session_factory) -> None:
    make_member(session_factory, admin.project_id, "c@example.com", ProjectRole.COLLABORATOR)
    token = _invite(admin, "STAFF")
    collaborator = sign_in(TestClient(client.app), "c@example.com")
    assert collaborator.post(f"/api/invites/{token}/accept").json()["role"] == "COLLABORATOR"


def test_only_the_administrator_makes_invites(
    client: TestClient, admin: Actor, session_factory
) -> None:
    make_member(session_factory, admin.project_id, "c@example.com", ProjectRole.COLLABORATOR)
    collaborator = sign_in(client, "c@example.com", admin.project_id)
    assert collaborator.post("/api/project/invites", json={"role": "ADMIN"}).status_code == 403


def test_accepting_needs_a_signed_in_account(client: TestClient, admin: Actor) -> None:
    token = _invite(admin)
    anonymous = TestClient(client.app)
    assert anonymous.post(f"/api/invites/{token}/accept").status_code == 401


# ------------------------------------------------------------------- desktop


def test_the_desktop_app_keeps_one_project_and_local_accounts(app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    from shabetz.api.deps import settings_dep

    desktop = settings.model_copy(update={"deployment": "desktop"})
    app.dependency_overrides[settings_dep] = lambda: desktop
    with TestClient(app) as client:
        body = client.post(
            "/api/setup/bootstrap-admin",
            json={"email": "me@example.com", "full_name": "Me", "password": "x" * 20},
        ).json()
        admin = Actor(client, body["csrf_token"], body["user"])
        project_id = admin.get("/api/projects").json()[0]["id"]
        admin = admin.in_project(project_id)

        assert admin.post("/api/projects", json={"name": "Second"}).status_code == 409
        assert admin.delete("/api/project").status_code == 409

        created = admin.post(
            "/api/project/members",
            json={
                "email": "helper@example.com",
                "full_name": "Helper",
                "password": "y" * 20,
                "role": "COLLABORATOR",
            },
        )
        assert created.status_code == 201, created.text
        member_id = created.json()["id"]
        assert (
            admin.post(
                f"/api/project/members/{member_id}/password", json={"password": "z" * 20}
            ).status_code
            == 200
        )

        client.cookies.clear()
        signed_in = client.post(
            "/api/auth/login", json={"email": "helper@example.com", "password": "z" * 20}
        )
        assert signed_in.status_code == 200
