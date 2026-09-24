"""Settings accept database URLs as hosting providers hand them out."""

from __future__ import annotations

import pytest

from shabetz.config import Settings


@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@db.example.com:5432/shabetz",
        "postgresql://u:p@db.example.com:5432/shabetz",
    ],
)
def test_a_provider_postgres_url_uses_the_installed_driver(given: str) -> None:
    # Render and Heroku name no driver; SQLAlchemy would then want psycopg2,
    # which is not installed.
    assert (
        Settings(database_url=given).database_url
        == "postgresql+psycopg://u:p@db.example.com:5432/shabetz"
    )


@pytest.mark.parametrize(
    "given",
    [
        "postgresql+psycopg://u:p@db/shabetz",
        "mysql+pymysql://u:p@db:3306/shabetz?charset=utf8mb4",
        "sqlite:///shabetz.db",
    ],
)
def test_other_urls_are_left_alone(given: str) -> None:
    assert Settings(database_url=given).database_url == given
