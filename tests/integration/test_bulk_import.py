"""Bulk entry: pasted lists and a roster imported from a spreadsheet."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from tests.integration.conftest import Actor

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def _names(actor: Actor, path: str) -> list[str]:
    response = actor.get(path)
    assert response.status_code == 200, response.text
    return [row["name"] for row in response.json()]


# ------------------------------------------------------------- pasted lists


def test_pasted_divisions_are_added_once_in_order(admin: Actor) -> None:
    first = admin.post("/api/config/divisions/bulk", json={"names": ["North", "South", " "]})
    assert first.status_code == 200, first.text
    assert first.json() == {"created": ["North", "South"], "existing": []}

    # Pasting an overlapping list adds only what is missing, whatever the case.
    second = admin.post("/api/config/divisions/bulk", json={"names": ["south", "East", "EAST"]})
    assert second.json() == {"created": ["East"], "existing": ["South"]}

    assert _names(admin, "/api/config/divisions") == ["North", "South", "East"]


def test_a_removed_division_comes_back_instead_of_colliding(admin: Actor) -> None:
    admin.post("/api/config/divisions/bulk", json={"names": ["North"]})
    division_id = admin.get("/api/config/divisions").json()[0]["id"]
    assert admin.delete(f"/api/config/divisions/{division_id}").status_code == 204

    again = admin.post("/api/config/divisions/bulk", json={"names": ["North"]})
    assert again.status_code == 200, again.text
    assert again.json()["created"] == ["North"]
    assert _names(admin, "/api/config/divisions") == ["North"]


def test_levels_stack_above_the_ladder_even_after_one_was_removed(admin: Actor) -> None:
    admin.post(
        "/api/config/proficiency-levels/bulk",
        json={"names": ["Beginner", "Skilled", "Expert"]},
    )
    expert = admin.get("/api/config/proficiency-levels").json()[-1]
    admin.delete(f"/api/config/proficiency-levels/{expert['id']}")

    # The removed level still holds its rank; a new rung must not reuse it.
    response = admin.post("/api/config/proficiency-levels/bulk", json={"names": ["Master"]})
    assert response.status_code == 200, response.text
    assert _names(admin, "/api/config/proficiency-levels") == ["Beginner", "Skilled", "Master"]


def test_pasted_skills_and_shift_windows(admin: Actor) -> None:
    admin.post("/api/config/skills/bulk", json={"names": ["Driving", "First aid", "driving"]})
    assert _names(admin, "/api/config/skills") == ["Driving", "First aid"]

    response = admin.post(
        "/api/config/shift-templates/bulk",
        json={
            "templates": [
                {"name": "Morning", "start_hour": 6, "duration_hours": 8},
                {"name": "Night", "start_hour": 22, "duration_hours": 8},
                {"name": "morning", "start_hour": 7, "duration_hours": 1},
            ]
        },
    )
    assert response.json() == {"created": ["Morning", "Night"], "existing": ["morning"]}


def test_only_administrators_add_in_bulk(client: TestClient, admin: Actor) -> None:
    admin.post(
        "/api/users",
        json={
            "email": "s@example.com",
            "full_name": "S",
            "role": "SCHEDULER",
            "password": "a-long-enough-password",
        },
    )
    client.cookies.clear()
    body = client.post(
        "/api/auth/login", json={"email": "s@example.com", "password": "a-long-enough-password"}
    ).json()
    scheduler = Actor(client, body["csrf_token"], body["user"])
    response = scheduler.post("/api/config/divisions/bulk", json={"names": ["X"]})
    assert response.status_code == 403


def test_a_duplicate_name_is_a_conflict_not_a_server_error(admin: Actor) -> None:
    admin.post("/api/config/skills", json={"name": "Driving"})
    response = admin.post("/api/config/skills", json={"name": "Driving"})
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE"


# ------------------------------------------------------------ roster import


def _setup(admin: Actor) -> None:
    admin.post("/api/config/divisions/bulk", json={"names": ["North"]})
    admin.post("/api/config/proficiency-levels/bulk", json={"names": ["Basic", "Expert"]})
    admin.post("/api/config/skills/bulk", json={"names": ["Driving"]})


COLUMNS = [
    {"role": "name"},
    {"role": "division"},
    {"role": "days"},
    {"role": "skill", "skill_name": "Driving"},
    {"role": "skill", "skill_name": "Medic"},
]

ROWS = [
    ["Dana Cohen", "North", "א-ה", "Expert", ""],
    ["Avi Levi", "South", "Mon-Fri", "", "x"],
    ["Noa", "", "someday", "", ""],
    ["Ori", "North", "", "Wizard", ""],
    ["", "", "", "", ""],
    ["dana cohen", "North", "", "", ""],
]


def test_import_preview_writes_nothing_and_explains_each_row(admin: Actor) -> None:
    _setup(admin)
    response = admin.post(
        "/api/config/import/people",
        json={"columns": COLUMNS, "rows": ROWS, "default_weekdays": [SUN, MON, TUE, WED, THU]},
    )
    assert response.status_code == 200, response.text
    plan = response.json()

    assert plan["applied"] is False
    assert plan["to_create"] == 2
    # Created only because a row that will import needs them.
    assert plan["new_divisions"] == ["South"]
    assert plan["new_skills"] == ["Medic"]

    by_line = {row["line"]: row for row in plan["rows"]}
    assert set(by_line) == {1, 2, 3, 4, 6}  # the blank row is not reported
    assert by_line[1]["status"] == "create"
    assert by_line[1]["working_weekdays"] == [MON, TUE, WED, THU, SUN]
    assert by_line[1]["skills"] == {"Driving": "Expert"}
    # A tick means the lowest rung.
    assert by_line[2]["skills"] == {"Medic": "Basic"}
    assert [p["code"] for p in by_line[3]["problems"]] == ["missing_division", "bad_days"]
    assert by_line[4]["problems"] == [{"code": "unknown_level", "value": "Wizard"}]
    assert by_line[6]["problems"][0]["code"] == "duplicate_in_file"

    assert admin.get("/api/config/people").json() == []
    assert _names(admin, "/api/config/divisions") == ["North"]


def test_import_applies_the_valid_rows(admin: Actor) -> None:
    _setup(admin)
    response = admin.post(
        "/api/config/import/people",
        json={"columns": COLUMNS, "rows": ROWS, "default_weekdays": [MON], "apply": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True

    people = {p["full_name"]: p for p in admin.get("/api/config/people").json()}
    assert set(people) == {"Dana Cohen", "Avi Levi"}
    assert _names(admin, "/api/config/divisions") == ["North", "South"]
    assert _names(admin, "/api/config/skills") == ["Driving", "Medic"]
    assert people["Avi Levi"]["working_weekdays"] == [MON, TUE, WED, THU, FRI]

    # Importing the same file again adds nobody.
    again = admin.post(
        "/api/config/import/people",
        json={"columns": COLUMNS, "rows": ROWS, "default_weekdays": [MON], "apply": True},
    ).json()
    assert again["to_create"] == 0
    assert {r["status"] for r in again["rows"] if r["full_name"] == "Dana Cohen"} == {"exists"}
    assert len(admin.get("/api/config/people").json()) == 2


def test_plain_list_of_names_goes_to_the_chosen_division(admin: Actor) -> None:
    _setup(admin)
    north = admin.get("/api/config/divisions").json()[0]["id"]
    response = admin.post(
        "/api/config/import/people",
        json={
            "columns": [{"role": "name"}],
            "rows": [["Dana"], ["Avi"]],
            "default_division_id": north,
            "default_weekdays": [SUN, MON],
            "apply": True,
        },
    )
    assert response.json()["to_create"] == 2
    people = admin.get("/api/config/people").json()
    assert {p["division_id"] for p in people} == {north}
    assert all(p["working_weekdays"] == [MON, SUN] for p in people)


def test_import_needs_exactly_one_name_column(admin: Actor) -> None:
    response = admin.post(
        "/api/config/import/people",
        json={"columns": [{"role": "division"}], "rows": [["North"]]},
    )
    assert response.status_code == 422


def test_uploaded_workbook_becomes_rows(admin: Actor) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["שם", "מחלקה"])
    sheet.append(["דנה", "צפון"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    response = admin.post(
        "/api/config/import/table",
        files={"file": ("roster.xlsx", buffer.getvalue(), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"rows": [["שם", "מחלקה"], ["דנה", "צפון"]]}


def test_unsupported_upload_is_explained(admin: Actor) -> None:
    response = admin.post(
        "/api/config/import/table",
        files={"file": ("roster.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_FILE"
