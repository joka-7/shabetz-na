"""Engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings


def _configure_sqlite(engine: Engine) -> None:
    """Make SQLite behave like the database the application was written for.

    SQLite ignores foreign keys unless asked, so ON DELETE CASCADE would silently
    do nothing. WAL lets reads continue during a write, and the busy timeout
    makes a brief write collision wait instead of failing with "database is
    locked" -- both matter because the desktop app serves requests on several
    threads.
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    kwargs: dict[str, object] = {"pool_pre_ping": True, "future": True}
    if url.startswith("mysql"):
        # Recycle below MySQL's default eight-hour idle timeout so a long-lived
        # worker never hands out a connection the server has already dropped.
        kwargs["pool_recycle"] = 3600
    if url.startswith("sqlite"):
        # Requests run on a thread pool, so a connection may be used by a
        # thread other than the one that opened it.
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
