"""MySQL schema guarantees.

Rendered through the MySQL dialect rather than executed, so these hold in any
environment.  They cover the choices that are painful to retrofit once a
database carries real data.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import create_mock_engine

from shabetz.db.models import Base


@pytest.fixture(scope="module")
def mysql_ddl() -> str:
    statements: list[str] = []
    engine = create_mock_engine(
        "mysql+pymysql://",
        lambda sql, *a, **kw: statements.append(str(sql.compile(dialect=engine.dialect))),
    )
    Base.metadata.create_all(engine, checkfirst=False)
    return "\n".join(statements)


def test_every_table_is_utf8mb4(mysql_ddl: str) -> None:
    """MySQL's 'utf8' is a three-byte subset that mangles non-BMP characters."""
    creates = [s for s in mysql_ddl.split("CREATE TABLE") if s.strip()]
    assert creates
    for statement in creates:
        assert "CHARSET=utf8mb4" in statement
        assert not re.search(r"CHARSET=utf8\b(?!mb4)", statement)


def test_every_table_uses_innodb_and_a_unicode_collation(mysql_ddl: str) -> None:
    for statement in mysql_ddl.split("CREATE TABLE")[1:]:
        assert "ENGINE=InnoDB" in statement
        assert "utf8mb4_unicode_ci" in statement


def test_timestamps_are_datetime6_not_timestamp(mysql_ddl: str) -> None:
    """TIMESTAMP is 32-bit and expires in 2038, inside a planning horizon."""
    assert "DATETIME(6)" in mysql_ddl
    assert not re.search(r"\bTIMESTAMP\b", mysql_ddl)


def test_indexed_text_columns_are_bounded(mysql_ddl: str) -> None:
    """InnoDB cannot index unbounded TEXT, and its key limit is 3072 bytes."""
    offenders = [
        line.strip()
        for line in mysql_ddl.splitlines()
        if re.search(r"\bTEXT\b", line) and ("UNIQUE" in line or "PRIMARY KEY" in line)
    ]
    assert offenders == []


def test_bounded_columns_fit_within_the_innodb_key_limit(mysql_ddl: str) -> None:
    """At four bytes per utf8mb4 character the ceiling is 768 characters."""
    too_long = [
        int(match) for match in re.findall(r"VARCHAR\((\d+)\)", mysql_ddl) if int(match) > 768
    ]
    assert too_long == []


def test_schedule_payload_uses_longblob(mysql_ddl: str) -> None:
    """A long horizon on a large roster exceeds BLOB's 64 KiB ceiling."""
    assert "payload_gz LONGBLOB" in mysql_ddl


def test_json_columns_are_native(mysql_ddl: str) -> None:
    assert "params_json JSON" in mysql_ddl
    assert "settings_json JSON" in mysql_ddl


def test_non_ascii_names_round_trip() -> None:
    """Names outside ASCII must survive storage; the project is Hebrew-named."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    from shabetz.db.models import Division, Project

    hebrew = "מחלקת אלפא"
    with Session(engine) as db:
        project = Project(name="פרויקט")
        db.add(project)
        db.flush()
        db.add(Division(project_id=project.id, name=hebrew, display_order=0))
        db.commit()
        assert db.scalar(select(Division.name)) == hebrew
