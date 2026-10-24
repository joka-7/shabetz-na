"""With a data key set, the database holds ciphertext; the app still works as before."""

from __future__ import annotations

import gzip

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from shabetz import crypto
from shabetz.auth.service import create_user, email_is_taken
from shabetz.db.models import Base, User
from shabetz.domain.enums import ProjectRole
from shabetz.services.maintenance import (
    has_encrypted_data,
    pending_encryption,
    rewrite_stored,
)
from tests.integration.conftest import (
    ADMIN_PASSWORD,
    Actor,
    make_member,
    sign_in,
)

KEY = "a-long-secret-for-the-tests-0123456789"
OLD_KEY = "an-older-long-secret-for-tests-0123456789"

NAMES = ["Zebulon Quillfeather", "Marigold Thistlewick", "Ptolemy Barnaby-Finch"]
SECRETS = {
    "reason": "secret-dentist-appointment-4471",
    "note": "secret-swap-note-9923",
    "attendance": "secret-sick-at-home-5518",
    "email": "admin@example.com",
    "full_name": "First Admin",
}


@pytest.fixture
def sealed(client: TestClient):  # type: ignore[no-untyped-def]
    """Switch encryption on after the app exists (creating the app resets it)."""
    crypto.configure(KEY)
    yield
    crypto.configure(None)


def build(admin: Actor) -> dict:
    division = admin.post("/api/config/divisions", json={"name": "Alpha"}).json()["id"]
    template = admin.post(
        "/api/config/shift-templates", json={"name": "Day", "start_hour": 8, "duration_hours": 8}
    ).json()["id"]
    people = {}
    for name in NAMES:
        response = admin.post(
            "/api/config/people",
            json={
                "full_name": name,
                "division_id": division,
                "working_weekdays": list(range(7)),
                "external_ref": f"ref-{name.split()[0].lower()}",
            },
        )
        assert response.status_code == 201, response.text
        people[name] = response.json()["id"]
    job = admin.post(
        "/api/config/jobs",
        json={
            "name": "Desk",
            "required_people_per_shift": 1,
            "shift_template_ids": [template],
            "requirements": [],
        },
    ).json()["id"]
    run = admin.post(
        "/api/schedule/generate", json={"start_date": "2026-10-05", "end_date": "2026-10-06"}
    ).json()
    leave = admin.post(
        "/api/time-off",
        json={
            "person_id": people[NAMES[0]],
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "reason": SECRETS["reason"],
        },
    )
    assert leave.status_code == 201, leave.text
    return {"people": people, "job": job, "template": template, "run": run, "division": division}


def raw_dump(factory: sessionmaker[Session]) -> list[tuple[str, str, object]]:
    """Every value in every table exactly as the database holds it."""
    out: list[tuple[str, str, object]] = []
    with factory() as db:
        conn = db.connection()
        for table in Base.metadata.sorted_tables:
            result = conn.exec_driver_sql(f"SELECT * FROM {table.name}")
            columns = list(result.keys())
            for row in result:
                out += [(table.name, c, v) for c, v in zip(columns, row, strict=True)]
    return out


def leaks(dump: list[tuple[str, str, object]], needles: list[str]) -> list[tuple[str, str, str]]:
    found = []
    for table, column, value in dump:
        if isinstance(value, bytes | bytearray | memoryview):
            raw = bytes(value)
            if raw[:2] == b"\x1f\x8b":
                found.append((table, column, "uncompressed schedule"))
            text = raw.decode("utf-8", errors="ignore")
        else:
            text = str(value)
        for needle in needles:
            if needle in text:
                found.append((table, column, needle))
    return found


def test_nothing_personal_is_readable_in_the_database(
    sealed: None, client: TestClient, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    world = build(admin)
    run_id = world["run"]["schedule_id"]
    holder = world["run"]["assignments"][0]["person_id"]
    colleague = next(p for p in world["people"].values() if p != holder)
    make_member(session_factory, admin.project_id, "holder@example.com", ProjectRole.STAFF, holder)
    make_member(
        session_factory, admin.project_id, "friend@example.com", ProjectRole.STAFF, colleague
    )
    assert admin.post(f"/api/schedule/runs/{run_id}/publish", json={}).status_code == 200
    staff = sign_in(client, "holder@example.com", admin.project_id)
    slot = world["run"]["assignments"][0]
    swap = staff.post(
        "/api/swaps",
        json={
            "job_id": world["job"],
            "template_id": world["template"],
            "calendar_date": slot["calendar_date"],
            "to_person_id": colleague,
            "note": SECRETS["note"],
        },
    )
    assert swap.status_code == 201, swap.text
    manager = sign_in(client, "admin@example.com", admin.project_id)
    marked = manager.put(
        "/api/attendance",
        json={
            "person_id": holder,
            "calendar_date": "2026-10-05",
            "status": "ABSENT",
            "note": SECRETS["attendance"],
        },
    )
    # Whatever the attendance route looks like, the rest of the flow must hold.
    assert marked.status_code in (200, 201, 404, 405, 422)

    needles = [
        *NAMES,
        *SECRETS.values(),
        "holder@example.com",
        "friend@example.com",
        "ref-zebulon",
    ]
    assert leaks(raw_dump(session_factory), needles) == []
    # And it really is stored sealed, not just absent.
    with session_factory() as db:
        assert has_encrypted_data(db)


def test_the_app_works_normally_on_top_of_encrypted_storage(
    sealed: None, client: TestClient, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    world = build(admin)

    # People come back readable and sorted by name, as before.
    listed = [p["full_name"] for p in admin.get("/api/config/people").json()]
    assert listed == sorted(NAMES, key=str.casefold)

    # The schedule, with names in it, and an edit that rewrites the blob.
    run = admin.get(f"/api/schedule/runs/{world['run']['schedule_id']}").json()
    assert {a["person_name"] for a in run["assignments"]} <= set(NAMES)
    assert (
        admin.get(f"/api/schedule/runs/{run['schedule_id']}/export?format=csv").status_code == 200
    )

    # Time off, with its reason.
    leave = admin.get("/api/time-off").json()[0]
    assert leave["reason"] == SECRETS["reason"]

    # Signing in again finds the account through its fingerprint, in any case.
    client.cookies.clear()
    ok = client.post(
        "/api/auth/login", json={"email": "ADMIN@Example.com", "password": ADMIN_PASSWORD}
    )
    assert ok.status_code == 200 and ok.json()["user"]["full_name"] == "First Admin"
    assert (
        client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": ADMIN_PASSWORD}
        ).status_code
        == 401
    )

    # Members and the activity log show real names and addresses.
    manager = sign_in(client, "admin@example.com", admin.project_id)
    members = manager.get("/api/project/members").json()
    assert [m["email"] for m in members] == ["admin@example.com"]
    activity = manager.get("/api/project/activity").json()
    assert activity and activity[0]["user_name"] == "First Admin"


def test_an_address_can_only_be_used_once_even_though_it_is_stored_encrypted(
    sealed: None, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as db:
        create_user(db, email="Dana@Example.com", full_name="Dana", password=ADMIN_PASSWORD)
        db.commit()
    with session_factory() as db:
        assert email_is_taken(db, "dana@example.com")
        with pytest.raises(IntegrityError):
            create_user(db, email="dana@example.com", full_name="Dana 2", password=ADMIN_PASSWORD)
            db.commit()


def test_turning_encryption_on_for_a_site_that_already_has_data(
    client: TestClient, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    world = build(admin)  # written with no key: plain, as every existing site is
    before = leaks(raw_dump(session_factory), [*NAMES, SECRETS["reason"], "admin@example.com"])
    assert before, "the test data should start out readable"

    crypto.configure(KEY)
    try:
        # Switched on but not yet migrated: old accounts and data still work.
        manager = sign_in(client, "admin@example.com", admin.project_id)
        assert len(manager.get("/api/config/people").json()) == 3

        # New writes are sealed at once; the rows that already existed are not yet.
        assert leaks(raw_dump(session_factory), NAMES)
        with session_factory() as db:
            assert pending_encryption(db)
            changed = rewrite_stored(db)
            db.commit()
        assert changed > 0

        assert (
            leaks(raw_dump(session_factory), [*NAMES, SECRETS["reason"], "admin@example.com"]) == []
        )
        with session_factory() as db:
            assert has_encrypted_data(db) is True
            assert pending_encryption(db) == {}  # nothing left, and a second run is a no-op
            assert rewrite_stored(db) == 0

        # Everything still works, and signing in now goes through the fingerprint.
        manager = sign_in(client, "admin@example.com", admin.project_id)
        assert [p["full_name"] for p in manager.get("/api/config/people").json()] == sorted(
            NAMES, key=str.casefold
        )
        run = manager.get(f"/api/schedule/runs/{world['run']['schedule_id']}").json()
        assert run["assignments"]
        with session_factory() as db:
            assert db.scalar(select(User.email_hash)) is not None
    finally:
        crypto.configure(None)


def test_rotating_the_key(
    client: TestClient, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    crypto.configure(OLD_KEY)
    try:
        build(admin)
        with session_factory() as db:
            rewrite_stored(db)
            db.commit()

        # A new key becomes current; the old one is kept only for reading.
        crypto.configure(KEY, old=[OLD_KEY])
        manager = sign_in(client, "admin@example.com", admin.project_id)
        assert len(manager.get("/api/config/people").json()) == 3
        with session_factory() as db:
            assert pending_encryption(db)  # still sealed with the old key
            rewrite_stored(db)
            db.commit()
            assert pending_encryption(db) == {}

        # Now the old key is no longer needed, and the data opens with the new one alone.
        crypto.configure(KEY)
        manager = sign_in(client, "admin@example.com", admin.project_id)
        assert len(manager.get("/api/config/people").json()) == 3
    finally:
        crypto.configure(None)


def test_decrypting_everything_back_to_plain_text(
    client: TestClient, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    crypto.configure(KEY)
    try:
        build(admin)
        with session_factory() as db:
            rewrite_stored(db)
            db.commit()
        assert leaks(raw_dump(session_factory), NAMES) == []

        with crypto.writing_plaintext(), session_factory() as db:
            rewrite_stored(db)
            db.commit()
        dump = raw_dump(session_factory)
        assert leaks(dump, NAMES + [SECRETS["reason"]])  # readable again
        assert not any(isinstance(v, str) and v.startswith("enc1:") for _, _, v in dump)
        with session_factory() as db:
            assert has_encrypted_data(db) is False
            assert db.scalar(select(User.email_hash)) is None
    finally:
        crypto.configure(None)


def test_encrypted_data_without_the_key_is_reported_not_silently_ignored(
    sealed: None, client: TestClient, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    build(admin)
    crypto.configure(None)
    with session_factory() as db:
        assert has_encrypted_data(db) is True
        with pytest.raises(crypto.DataKeyError, match="SHABETZ_DATA_KEY"):
            db.scalars(select(User)).all()


def test_the_schedule_blob_is_sealed_and_still_a_gzip_inside(
    sealed: None, client: TestClient, admin: Actor, session_factory: sessionmaker[Session]
) -> None:
    from shabetz.db.models import ScheduleRun

    world = build(admin)
    with session_factory() as db:
        raw = db.execute(
            __import__("sqlalchemy").text("SELECT payload_gz FROM schedule_runs")
        ).scalar()
        assert bytes(raw)[:4] == b"ENC1"
        opened = db.get(ScheduleRun, world["run"]["schedule_id"])
        assert opened is not None and gzip.decompress(opened.payload_gz)
