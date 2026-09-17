"""Engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    kwargs: dict[str, object] = {"pool_pre_ping": True, "future": True}
    if settings.database_url.startswith("mysql"):
        # Recycle below MySQL's default eight-hour idle timeout so a long-lived
        # worker never hands out a connection the server has already dropped.
        kwargs["pool_recycle"] = 3600
    return create_engine(settings.database_url, **kwargs)


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
