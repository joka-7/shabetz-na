"""Declarative base and MySQL-aware column conventions.

The charset and length choices here are not incidental.  MySQL's ``utf8`` is a
three-byte subset that mangles anything outside the Basic Multilingual Plane, so
every table is explicitly ``utf8mb4``.  InnoDB's index key limit is 3072 bytes,
which at four bytes per character leaves 768 characters, so any column that is
indexed or unique is given an explicit bounded length rather than ``TEXT``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, MetaData, String
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

TABLE_ARGS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class UtcDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetimes stored as UTC.

    ``DATETIME(6)`` rather than ``TIMESTAMP``: the latter is 32-bit and stops
    working in 2038, which is well within the planning horizon of a scheduling
    application.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):  # type: ignore[no-untyped-def]
        # Microsecond precision has to be requested explicitly on MySQL, and the
        # argument only exists on that dialect's type.
        if dialect.name == "mysql":
            return dialect.type_descriptor(MYSQL_DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class StrEnumType(TypeDecorator[Any]):
    """A string column that round-trips as its enum member.

    Declaring ``Mapped[SomeEnum]`` over a plain ``String`` stores the value but
    loads a bare ``str`` back, so every ``x is SomeEnum.MEMBER`` comparison
    silently evaluates False while ``==`` still passes. That reads as working
    code and fails quietly, so the coercion belongs in the column type rather
    than in each comparison.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[Enum], length: int = 32) -> None:
        self._enum_class = enum_class
        super().__init__(length=length)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, self._enum_class):
            return str(value.value)
        # Accept the raw value too, so a plain string from an API payload is
        # still validated against the enum rather than stored blindly.
        return str(self._enum_class(value).value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return self._enum_class(value)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(UTC)
