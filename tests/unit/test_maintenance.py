"""Desktop backups and pruning old draft schedules."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from shabetz.db.models import Base, Project, ScheduleRun
from shabetz.services.maintenance import backup_sqlite, cleanup


def test_a_backup_is_a_working_copy_and_only_the_newest_are_kept(tmp_path: Path) -> None:
    database = tmp_path / "shabetz.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE t (x)")
        db.execute("INSERT INTO t VALUES (42)")
    folder = tmp_path / "backups"
    made = [backup_sqlite(database, folder, keep=3) for _ in range(5)]

    kept = sorted(p.name for p in folder.iterdir())
    assert kept == sorted(p.name for p in made[-3:])
    with sqlite3.connect(made[-1]) as copy:
        assert copy.execute("SELECT x FROM t").fetchone() == (42,)


def test_draft_pruning_keeps_the_newest_and_every_published_schedule() -> None:
    from datetime import timedelta

    from shabetz.db.base import utcnow

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project = Project(name="P")
        db.add(project)
        db.flush()
        now = utcnow()
        for i in range(5):
            db.add(
                ScheduleRun(
                    id=f"draft-{i}",
                    project_id=project.id,
                    params_json={},
                    summary_json={},
                    payload_gz=b"",
                    created_at=now - timedelta(days=i),
                )
            )
        db.add(
            ScheduleRun(
                id="published",
                project_id=project.id,
                params_json={},
                summary_json={},
                payload_gz=b"",
                created_at=now - timedelta(days=30),
                published_at=now,
            )
        )
        db.flush()

        assert cleanup(db).drafts == 0  # nothing is deleted unless asked
        report = cleanup(db, keep_drafts=2)
        left = set(db.scalars(select(ScheduleRun.id)))
    assert report.drafts == 3
    assert left == {"draft-0", "draft-1", "published"}


def test_a_schedule_is_parsed_once_and_an_edit_is_never_served_stale() -> None:
    import gzip
    import json

    from shabetz.db.models import ScheduleRun
    from shabetz.services.orchestration import JobOrchestrationService

    def run_with(assignments: list) -> ScheduleRun:
        blob = gzip.compress(json.dumps({"assignments": assignments, "warnings": []}).encode())
        return ScheduleRun(id="r", project_id=1, params_json={}, summary_json={}, payload_gz=blob)

    first = run_with([{"person_id": 1}])
    once = JobOrchestrationService.load_payload(first)
    assert JobOrchestrationService.load_payload(run_with([{"person_id": 1}])) is once

    # The same schedule id with different content -- an edit -- reads as new.
    edited = run_with([{"person_id": 2}])
    assert JobOrchestrationService.load_payload(edited)["assignments"] == [{"person_id": 2}]
