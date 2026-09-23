"""Google sign-in: the security properties of the flow.

Nothing here contacts Google. The parts worth pinning are local: that the state
parameter is actually checked, that a tampered or stale cookie is refused, and
that an unverified email address cannot be used to claim an account.
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from shabetz.auth import google

SECRET = "a-test-secret-key"
REDIRECT = "http://localhost:5173/auth/google/callback"


def _start() -> tuple[dict[str, list[str]], str]:
    url, cookie = google.begin(
        client_id="client-id.apps.googleusercontent.com",
        redirect_uri=REDIRECT,
        secret_key=SECRET,
    )
    return parse_qs(urlparse(url).query), cookie


def test_authorize_url_targets_google_with_the_expected_parameters() -> None:
    params, _ = _start()
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == [REDIRECT]
    assert params["scope"] == ["openid email profile"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"][0]


def test_code_challenge_is_the_s256_hash_of_the_stored_verifier() -> None:
    """A challenge that did not derive from the verifier would make PKCE a no-op."""
    params, cookie = _start()
    stored = google._serializer(SECRET).loads(cookie)
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(stored["verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert params["code_challenge"] == [expected]


def test_each_start_is_unique() -> None:
    first, _ = _start()
    second, _ = _start()
    assert first["state"] != second["state"]
    assert first["code_challenge"] != second["code_challenge"]


async def _complete(cookie: str | None, state: str) -> google.GoogleIdentity:
    return await google.complete(
        code="an-auth-code",
        state=state,
        cookie_value=cookie,
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri=REDIRECT,
        secret_key=SECRET,
    )


@pytest.mark.asyncio
async def test_missing_cookie_is_refused() -> None:
    with pytest.raises(google.GoogleAuthError):
        await _complete(None, "any-state")


@pytest.mark.asyncio
async def test_state_mismatch_is_refused() -> None:
    """Without this check an attacker could complete someone else's callback."""
    _, cookie = _start()
    with pytest.raises(google.GoogleAuthError):
        await _complete(cookie, "not-the-state-we-issued")


@pytest.mark.asyncio
async def test_tampered_cookie_is_refused() -> None:
    params, cookie = _start()
    with pytest.raises(google.GoogleAuthError):
        await _complete(cookie[:-4] + "AAAA", params["state"][0])


@pytest.mark.asyncio
async def test_cookie_signed_with_another_key_is_refused() -> None:
    url, _ = google.begin(client_id="c", redirect_uri=REDIRECT, secret_key="a-different-secret")
    state = parse_qs(urlparse(url).query)["state"][0]
    foreign = google._serializer("a-different-secret").dumps({"state": state, "verifier": "v"})
    with pytest.raises(google.GoogleAuthError):
        await _complete(foreign, state)


def _mock_transport(
    *, token_status: int = 200, profile: dict | None = None, profile_status: int = 200
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(token_status, json={"access_token": "an-access-token"})
        return httpx.Response(profile_status, json=profile or {})

    return httpx.MockTransport(handler)


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    """Route the module's client at a mock transport.

    ``google.httpx`` is the httpx module itself, so the replacement has to close
    over the original class -- referring to ``httpx.AsyncClient`` inside it
    would call the replacement and recurse.
    """
    monkeypatch.setattr(
        google.httpx,
        "AsyncClient",
        lambda **kwargs: _REAL_ASYNC_CLIENT(transport=transport),
    )


@pytest.mark.asyncio
async def test_unverified_email_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unverified address proves nothing, and accounts are matched by email."""
    params, cookie = _start()
    transport = _mock_transport(
        profile={"sub": "123", "email": "someone@example.com", "email_verified": False}
    )
    _patch_client(monkeypatch, transport)
    with pytest.raises(google.GoogleAuthError, match="verified"):
        await _complete(cookie, params["state"][0])


@pytest.mark.asyncio
async def test_verified_profile_yields_an_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    params, cookie = _start()
    transport = _mock_transport(
        profile={
            "sub": "google-subject-123",
            "email": "dana@example.com",
            "email_verified": True,
            "name": "Dana Cohen",
        }
    )
    _patch_client(monkeypatch, transport)
    identity = await _complete(cookie, params["state"][0])
    assert identity.subject == "google-subject-123"
    assert identity.email == "dana@example.com"
    assert identity.full_name == "Dana Cohen"


@pytest.mark.asyncio
async def test_token_rejection_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    params, cookie = _start()
    transport = _mock_transport(token_status=400)
    _patch_client(monkeypatch, transport)
    with pytest.raises(google.GoogleAuthError):
        await _complete(cookie, params["state"][0])


@pytest.mark.asyncio
async def test_incomplete_profile_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    params, cookie = _start()
    transport = _mock_transport(profile={"email_verified": True, "email": "a@b.com"})
    _patch_client(monkeypatch, transport)
    with pytest.raises(google.GoogleAuthError):
        await _complete(cookie, params["state"][0])
