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
