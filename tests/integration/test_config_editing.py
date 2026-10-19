"""Every kind of configuration can be changed after it was created."""

from __future__ import annotations

from tests.integration.conftest import Actor


def test_skill_window_and_level_can_be_renamed_and_changed(admin: Actor) -> None:
    skill = admin.post("/api/config/skills", json={"name": "Medic"}).json()
    renamed = admin.put(f"/api/config/skills/{skill['id']}", json={"name": "Paramedic"})
    assert renamed.status_code == 200, renamed.text
    names = [s["name"] for s in admin.get("/api/config/skills").json()]
    assert names == ["Paramedic"]

    window = admin.post(
        "/api/config/shift-templates", json={"name": "Day", "start_hour": 8, "duration_hours": 8}
    ).json()
    changed = admin.put(
        f"/api/config/shift-templates/{window['id']}",
        json={"name": "Long day", "start_hour": 7.5, "duration_hours": 10},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["start_hour"] == 7.5

    low = admin.post("/api/config/proficiency-levels", json={"name": "Basic", "rank": 0}).json()
    high = admin.post("/api/config/proficiency-levels", json={"name": "Expert", "rank": 1}).json()
    clash = admin.put(
        f"/api/config/proficiency-levels/{high['id']}", json={"name": "Expert", "rank": 0}
    )
    assert clash.status_code == 409
    ok = admin.put(
        f"/api/config/proficiency-levels/{low['id']}", json={"name": "Novice", "rank": 0}
    )
    assert ok.status_code == 200
    assert ok.json()["name"] == "Novice"


def test_duplicate_names_are_reported_not_crashed(admin: Actor) -> None:
    admin.post("/api/config/skills", json={"name": "A"})
    b = admin.post("/api/config/skills", json={"name": "B"}).json()
    response = admin.put(f"/api/config/skills/{b['id']}", json={"name": "A"})
    assert response.status_code == 409


def test_editing_an_unknown_row_is_404(admin: Actor) -> None:
    assert admin.put("/api/config/skills/9999", json={"name": "X"}).status_code == 404
    assert (
        admin.put(
            "/api/config/shift-templates/9999",
            json={"name": "X", "start_hour": 1, "duration_hours": 1},
        ).status_code
        == 404
    )


def test_person_days_and_skills_can_be_edited_and_skill_deleted(admin: Actor) -> None:
    division = admin.post("/api/config/divisions", json={"name": "North"}).json()
    level = admin.post("/api/config/proficiency-levels", json={"name": "Basic", "rank": 0}).json()
    medic = admin.post("/api/config/skills", json={"name": "Medic"}).json()
    driver = admin.post("/api/config/skills", json={"name": "Driver"}).json()
    person = admin.post(
        "/api/config/people",
        json={
            "full_name": "Dana",
            "division_id": division["id"],
            "working_weekdays": [0, 1],
            "skills": [{"skill_id": medic["id"], "level_id": level["id"]}],
        },
    ).json()

    # Keeps existing days and skills while adding new ones.
    edited = admin.put(
        f"/api/config/people/{person['id']}",
        json={
            "full_name": "Dana",
            "division_id": division["id"],
            "working_weekdays": [0, 1, 2],
            "skills": [
                {"skill_id": medic["id"], "level_id": level["id"]},
                {"skill_id": driver["id"], "level_id": level["id"]},
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["working_weekdays"] == [0, 1, 2]
    assert len(edited.json()["skills"]) == 2

    assert admin.delete(f"/api/config/skills/{driver['id']}").status_code == 204
    people = admin.get("/api/config/people").json()
    assert [s["skill_id"] for s in people[0]["skills"]] == [medic["id"]]
    assert [s["name"] for s in admin.get("/api/config/skills").json()] == ["Medic"]


def test_part_day_time_off_is_stored_and_validated(admin: Actor) -> None:
    division = admin.post("/api/config/divisions", json={"name": "North"}).json()
    person = admin.post(
        "/api/config/people", json={"full_name": "Dana", "division_id": division["id"]}
    ).json()
    day = "2026-10-12"
    ok = admin.post(
        "/api/time-off",
        json={
            "person_id": person["id"],
            "start_date": day,
            "end_date": day,
            "start_hour": 9,
            "end_hour": 13.5,
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["start_hour"] == 9 and ok.json()["end_hour"] == 13.5
    backwards = admin.post(
        "/api/time-off",
        json={
            "person_id": person["id"],
            "start_date": day,
            "end_date": day,
            "start_hour": 13,
            "end_hour": 9,
        },
    )
    assert backwards.status_code == 422
