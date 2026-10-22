"""Who may sign in, and which forwarded address the throttles believe."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from shabetz.api.deps import client_address
from shabetz.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(secret_key="x", database_url="sqlite://", **overrides)  # type: ignore[arg-type]


def test_listed_addresses_match_whatever_their_case_and_spacing() -> None:
    settings = _settings(environment="prod", allowed_emails=" J@Example.com ,other@x.org")
    assert settings.email_is_allowed("j@example.com")
    assert settings.email_is_allowed("  OTHER@x.org")
    assert not settings.email_is_allowed("stranger@example.com")


def test_an_empty_list_fails_closed_only_in_production() -> None:
    assert not _settings(environment="prod").email_is_allowed("j@example.com")
    assert _settings(environment="dev").email_is_allowed("j@example.com")


def test_a_star_lets_anyone_in() -> None:
    assert _settings(environment="prod", allowed_emails="*").email_is_allowed("a@b.c")


def test_the_desktop_app_has_no_list() -> None:
    settings = _settings(environment="prod", deployment="desktop", allowed_emails="j@x.com")
    assert settings.email_is_allowed("anyone@example.com")


def test_the_unprefixed_variable_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_EMAILS", "j@example.com")
    assert Settings(secret_key="x", database_url="sqlite://").allowed_emails == "j@example.com"


def _request(forwarded: list[str], peer: str = "10.1.1.1") -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("hops", "forwarded", "expected"),
    [
        (0, ["1.1.1.1, 2.2.2.2"], "10.1.1.1"),  # no proxy: the socket's peer
        (1, ["1.1.1.1, 2.2.2.2"], "2.2.2.2"),  # the entry the proxy appended
        (2, ["1.1.1.1, 2.2.2.2"], "1.1.1.1"),
        (1, ["forged", "2.2.2.2"], "2.2.2.2"),  # repeated headers read as one list
        (3, ["1.1.1.1"], "10.1.1.1"),  # fewer entries than proxies: not trusted
    ],
)
def test_the_client_address_is_counted_from_the_right(
    hops: int, forwarded: list[str], expected: str
) -> None:
    settings = _settings(trusted_proxy_hops=hops)
    assert client_address(_request(forwarded), settings) == expected
