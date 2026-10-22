"""Saving a project to a file and merging it back in, here or somewhere else."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.conftest import Actor, make_account, sign_in


def _build(admin: Actor) -> None:
    """A small but complete organisation, through the same API the screens use."""
    for path, body in (
        ("/api/config/divisions/bulk", {"names": ["North", "South"]}),
        ("/api/config/proficiency-levels/bulk", {"names": ["Beginner", "Expert"]}),
        ("/api/config/skills/bulk", {"names": ["Driving"]}),
        (
            "/api/config/shift-templates/bulk",
            {"templates": [{"name": "Day", "start_hour": 8, "duration_hours": 8}]},
        ),
    ):
        assert admin.post(path, json=body).status_code == 200, path
    skill = admin.get("/api/config/skills").json()[0]
    expert = admin.get("/api/config/proficiency-levels").json()[1]
    template = admin.get("/api/config/shift-templates").json()[0]
    north = admin.get("/api/config/divisions").json()[0]
    job = admin.post(
        "/api/config/jobs",
        json={
            "name": "Patrol",
            "required_people_per_shift": 2,
            "shift_template_ids": [template["id"]],
            "requirements": [
                {"skill_id": skill["id"], "min_level_id": expert["id"], "required_count": 1}
            ],
        },
    )
    assert job.status_code == 201, job.text
    person = admin.post(
        "/api/config/people",
        json={
            "full_name": "Dana Cohen",
            "division_id": north["id"],
            "working_weekdays": [0, 1, 2],
            "skills": [{"skill_id": skill["id"], "level_id": expert["id"]}],
        },
    )
    assert person.status_code == 201, person.text
    off = admin.post(
        "/api/time-off",
        json={
            "person_id": person.json()["id"],
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
            "reason": "Trip",
        },
    )
    assert off.status_code == 201, off.text


def _backup(admin: Actor) -> dict:
    response = admin.get(f"/api/config/backup?project={admin.project_id}")
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    return response.json()


def _import(actor: Actor, backup: dict, *, apply: bool) -> dict:
    response = actor.post("/api/config/backup/import", json={"backup": backup, "apply": apply})
    assert response.status_code == 200, response.text
    return response.json()


def _fresh_project(client: TestClient, factory) -> Actor:  # type: ignore[no-untyped-def]
    make_account(factory, "other@example.com")
    other = sign_in(TestClient(client.app), "other@example.com")
    body = other.post("/api/projects", json={"name": "Copy"}).json()
    return other.in_project(body["id"])


def test_a_backup_holds_the_configuration_by_name(admin: Actor) -> None:
    _build(admin)
    backup = _backup(admin)
    assert backup["format"] == "shabetz-project"
    assert [d["name"] for d in backup["divisions"]] == ["North", "South"]
    assert [level["name"] for level in backup["levels"]] == ["Beginner", "Expert"]
    job = backup["jobs"][0]
    assert job["shift_templates"] == ["Day"]
    assert job["requirements"][0] == {
        "skill": "Driving",
        "min_level": "Expert",
        "required_count": 1,
        "is_leadership": False,
    }
    person = backup["people"][0]
    assert person["division"] == "North"
    assert person["skills"] == [{"skill": "Driving", "level": "Expert"}]
    assert backup["time_off"][0]["person"] == "Dana Cohen"


def test_a_backup_restores_into_another_project(
    client: TestClient, admin: Actor, session_factory
) -> None:
    _build(admin)
    backup = _backup(admin)
    copy = _fresh_project(client, session_factory)

    preview = _import(copy, backup, apply=False)
    assert preview["applied"] is False
    assert preview["counts"]["people"]["created"] == 1
    # The preview wrote nothing.
    assert copy.get("/api/config/people").json() == []

    done = _import(copy, backup, apply=True)
    assert done["applied"] is True and done["problems"] == []
    people = copy.get("/api/config/people").json()
    assert [p["full_name"] for p in people] == ["Dana Cohen"]
    assert people[0]["working_weekdays"] == [0, 1, 2]
    jobs = copy.get("/api/config/jobs").json()
    assert jobs[0]["required_people_per_shift"] == 2
    assert jobs[0]["requirements"][0]["skill_name"] == "Driving"
    assert len(copy.get("/api/time-off").json()) == 1

    # Same data again: nothing new, nothing changed.
    again = _import(copy, backup, apply=True)
    for entity, counts in again["counts"].items():
        assert counts["created"] == 0 and counts["updated"] == 0, entity


def test_importing_into_the_same_project_updates_without_removing(admin: Actor) -> None:
    _build(admin)
    backup = _backup(admin)
    admin.post(
        "/api/config/people",
        json={
            "full_name": "Someone Else",
            "division_id": admin.get("/api/config/divisions").json()[0]["id"],
        },
    )

    backup["jobs"][0]["required_people_per_shift"] = 3
    backup["people"][0]["working_weekdays"] = [4]
    result = _import(admin, backup, apply=True)
    assert result["counts"]["jobs"]["updated"] == 1
    assert result["counts"]["people"]["updated"] == 1

    assert admin.get("/api/config/jobs").json()[0]["required_people_per_shift"] == 3
    people = {p["full_name"]: p for p in admin.get("/api/config/people").json()}
    assert people["Dana Cohen"]["working_weekdays"] == [4]
    # Nobody the file does not mention is touched.
    assert "Someone Else" in people


def test_a_file_that_is_not_a_backup_is_refused(admin: Actor) -> None:
    response = admin.post(
        "/api/config/backup/import", json={"backup": {"hello": "world"}, "apply": True}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "BAD_BACKUP"


def test_a_job_naming_an_unknown_shift_window_is_reported_not_imported(admin: Actor) -> None:
    backup = {
        "format": "shabetz-project",
        "version": 1,
        "jobs": [{"name": "Ghost", "shift_templates": ["Nowhere"]}],
    }
    result = _import(admin, backup, apply=True)
    assert result["problems"] == [{"code": "unknown_shift_window", "value": "Ghost: Nowhere"}]
    assert admin.get("/api/config/jobs").json() == []


def test_viewers_and_staff_cannot_download_or_import(
    client: TestClient, admin: Actor, session_factory
) -> None:
    from shabetz.domain.enums import ProjectRole
    from tests.integration.conftest import make_member

    for email, role in (
        ("v@example.com", ProjectRole.VIEWER),
        ("s@example.com", ProjectRole.STAFF),
    ):
        make_member(session_factory, admin.project_id, email, role)
        other = sign_in(TestClient(client.app), email).in_project(admin.project_id)
        assert other.get(f"/api/config/backup?project={admin.project_id}").status_code == 403
        denied = other.post("/api/config/backup/import", json={"backup": {}, "apply": True})
        assert denied.status_code == 403
