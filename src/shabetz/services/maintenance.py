"""Housekeeping: clearing out dead rows, and backing up the desktop database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import LargeBinary, Text, delete, func, literal, select, type_coerce
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm.attributes import flag_modified

from .. import crypto
from ..auth.sessions import purge_stale
from ..db import models as orm
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


# ---------------------------------------------------------------- encryption at rest

# Every column that holds personal data, with the model that owns it.
ENCRYPTED_COLUMNS: tuple[tuple[type, str, bool], ...] = (
    (orm.User, "email", False),
    (orm.User, "full_name", False),
    (orm.Session, "user_agent", False),
    (orm.Person, "full_name", False),
    (orm.Person, "external_ref", False),
    (orm.TimeOff, "reason", False),
    (orm.TimeOff, "review_note", False),
    (orm.SwapRequest, "note", False),
    (orm.SwapRequest, "review_note", False),
    (orm.Attendance, "note", False),
    (orm.ScheduleRun, "payload_gz", True),
    (orm.AuditLog, "before_json", False),
    (orm.AuditLog, "after_json", False),
)

HEADER = 20  # enough of a stored value to tell how it was sealed
CHUNK = 100


def _primary_key(model: type) -> Any:
    return model.__mapper__.primary_key[0]  # type: ignore[attr-defined]


def _raw(column: Any, blob: bool) -> Any:
    """The column as the database stores it, skipping the decryption on the way out."""
    return type_coerce(column, LargeBinary() if blob else Text())


def _stale_rows(db: DbSession, model: type, columns: list[tuple[str, bool]]) -> list:
    """Primary keys of this model's rows not yet stored the way they should be."""
    cipher = crypto.sealing_cipher()
    key = _primary_key(model)
    heads = [func.substr(_raw(getattr(model, name), blob), 1, HEADER) for name, blob in columns]
    stale = []
    for pk, *values in db.execute(select(key, *heads)):
        for value, (_, blob) in zip(values, columns, strict=True):
            if value is None:
                continue
            sealed = crypto.is_sealed_blob(value) if blob else crypto.is_sealed_text(value)
            if cipher is None:
                needs = sealed
            else:
                needs = not sealed or not cipher.is_sealed_by_current_key(
                    bytes(value) if blob else value
                )
            if needs:
                stale.append(pk)
                break
    return stale


def pending_encryption(db: DbSession) -> dict[type, list]:
    """Rows whose personal data is not yet stored as the current key setting wants.

    With a key set that is plain values and values sealed with an older key;
    with none (while decrypting), any value still sealed.
    """
    by_model: dict[type, list[tuple[str, bool]]] = {}
    for model, name, blob in ENCRYPTED_COLUMNS:
        by_model.setdefault(model, []).append((name, blob))
    found = {model: _stale_rows(db, model, columns) for model, columns in by_model.items()}
    return {model: ids for model, ids in found.items() if ids}


def has_encrypted_data(db: DbSession) -> bool:
    """Whether anything in the database is stored encrypted."""
    for model, name, blob in ENCRYPTED_COLUMNS:
        column = _raw(getattr(model, name), blob)
        head = func.substr(column, 1, len(crypto.BLOB_MAGIC))
        if blob:
            if any(crypto.is_sealed_blob(h) for (h,) in db.execute(select(head))):
                return True
        elif db.scalar(
            select(literal(1)).where(head == "enc1:"[: len(crypto.BLOB_MAGIC)]).limit(1)
        ):
            return True
    return False


def rewrite_stored(db: DbSession) -> int:
    """Store every personal value the way the key setting says; returns rows changed.

    Reading goes through the same column types as the rest of the app, so each
    value is opened with whichever key sealed it, and writing it back seals it
    with the current one (or leaves it plain when decrypting). Safe to repeat:
    rows already in the right form are not touched.
    """
    names: dict[type, list[str]] = {}
    for model, name, _ in ENCRYPTED_COLUMNS:
        names.setdefault(model, []).append(name)

    changed = 0
    cipher = crypto.sealing_cipher()
    for model, ids in pending_encryption(db).items():
        key = _primary_key(model)
        for start in range(0, len(ids), CHUNK):
            chunk = ids[start : start + CHUNK]
            rows: Any = db.scalars(select(model).where(key.in_(chunk)))
            for row in rows:
                for name in names[model]:
                    flag_modified(row, name)
                if model is orm.User:
                    row.email_hash = cipher.email_hash(row.email) if cipher else None
            db.flush()
            db.expunge_all()
            changed += len(chunk)
    return changed
