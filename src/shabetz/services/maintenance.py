"""Housekeeping: clearing out dead rows, and backing up the desktop database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from ..auth.sessions import purge_stale
from ..db.base import utcnow
from ..db.models import Project, ProjectInvite, ScheduleRun

# Ended sessions and dead invite links are kept this long for the record.
KEEP_DAYS = 30
BACKUP_PREFIX = "shabetz-"
BACKUP_SUFFIX = ".db"


@dataclass(frozen=True)
class CleanupReport:
    sessions: int
    invites: int
    drafts: int


def cleanup(db: DbSession, *, keep_drafts: int | None = None) -> CleanupReport:
    """Delete sessions and invites that ended long ago, and optionally old drafts.

    ``keep_drafts`` keeps each project's newest unpublished schedules and
    deletes the rest; published schedules are never touched. Left as None,
    no schedule is deleted.
    """
    sessions = purge_stale(db, keep_days=KEEP_DAYS)
    cutoff = utcnow() - timedelta(days=KEEP_DAYS)
    invites = db.execute(
        delete(ProjectInvite).where(
            (ProjectInvite.expires_at < cutoff)
            | (ProjectInvite.revoked_at.is_not(None) & (ProjectInvite.revoked_at < cutoff))
        )
    ).rowcount  # type: ignore[attr-defined]

    drafts = 0
    if keep_drafts is not None:
        for project_id in db.scalars(select(Project.id)):
            stale = db.scalars(
                select(ScheduleRun.id)
                .where(ScheduleRun.project_id == project_id, ScheduleRun.published_at.is_(None))
                .order_by(ScheduleRun.created_at.desc())
                .offset(keep_drafts)
            ).all()
            if stale:
                drafts += db.execute(delete(ScheduleRun).where(ScheduleRun.id.in_(stale))).rowcount  # type: ignore[attr-defined]
    return CleanupReport(sessions=int(sessions), invites=int(invites or 0), drafts=drafts)


def backup_sqlite(database: Path, folder: Path, *, keep: int = 10) -> Path:
    """Copy a live SQLite database into ``folder``, keeping the newest ``keep``.

    ``VACUUM INTO`` writes a consistent copy even while the app has the
    database open, which copying the file itself would not guarantee.
    """
    folder.mkdir(parents=True, exist_ok=True)
    # Down to the microsecond, so names sort in the order they were made --
    # which is how the oldest are found -- even for several in one second.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = folder / f"{BACKUP_PREFIX}{stamp}{BACKUP_SUFFIX}"
    connection = sqlite3.connect(database)
    try:
        connection.execute("VACUUM INTO ?", (str(target),))
    finally:
        connection.close()
    backups = sorted(folder.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"), key=lambda p: p.name)
    for old in backups[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
    return target
