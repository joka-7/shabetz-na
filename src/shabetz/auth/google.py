"""Google OAuth 2.0 sign-in.

Authorization Code with PKCE. The transient state and code verifier ride in a
short-lived signed cookie rather than server-side session storage, so the flow
needs no session middleware and survives a worker restart mid-redirect.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer

AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

SCOPES = "openid email profile"
STATE_COOKIE = "shabetz_oauth_state"
STATE_MAX_AGE_SECONDS = 600
_SALT = "shabetz-google-oauth"


class GoogleAuthError(Exception):
    """The Google flow could not be completed."""


class GoogleIdentity:
    def __init__(self, subject: str, email: str, full_name: str) -> None:
        self.subject = subject
        self.email = email
        self.full_name = full_name


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=_SALT)


def _challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def begin(*, client_id: str, redirect_uri: str, secret_key: str) -> tuple[str, str]:
    """Build the redirect URL and the signed cookie value guarding it.

    The ``state`` parameter is what stops an attacker completing someone
    else's callback, so it is generated here and checked on return.
    """
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": _challenge_for(verifier),
        "code_challenge_method": "S256",
        # Ask for an account each time rather than silently reusing whichever
        # Google session the browser happens to hold.
        "prompt": "select_account",
    }
    url = f"{AUTHORIZE_ENDPOINT}?{httpx.QueryParams(params)}"
    cookie = _serializer(secret_key).dumps({"state": state, "verifier": verifier})
    return url, cookie


async def complete(
    *,
    code: str,
    state: str,
    cookie_value: str | None,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    secret_key: str,
) -> GoogleIdentity:
    if not cookie_value:
        raise GoogleAuthError("Sign-in did not start in this browser")

    try:
        stored: dict[str, Any] = _serializer(secret_key).loads(
            cookie_value, max_age=STATE_MAX_AGE_SECONDS
        )
    except BadSignature as exc:
        raise GoogleAuthError("Sign-in request expired or was tampered with") from exc

    # Compared in constant time: a mismatch means this callback belongs to a
    # different request than the one this browser started.
    if not secrets.compare_digest(str(stored.get("state", "")), state):
        raise GoogleAuthError("Sign-in request did not match")

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code_verifier": stored["verifier"],
            },
        )
        if token_response.status_code != 200:
            raise GoogleAuthError("Google rejected the sign-in")

        access_token = token_response.json().get("access_token")
        if not access_token:
            raise GoogleAuthError("Google returned no access token")

        userinfo_response = await client.get(
            USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
        )
        if userinfo_response.status_code != 200:
            raise GoogleAuthError("Could not read the Google profile")

    profile = userinfo_response.json()
    subject = profile.get("sub")
    email = profile.get("email")

    # An unverified address proves nothing about who owns it, and the account
    # lookup downstream is by email.
    if not profile.get("email_verified"):
        raise GoogleAuthError("This Google account has no verified email address")
    if not subject or not email:
        raise GoogleAuthError("Google returned an incomplete profile")

    return GoogleIdentity(
        subject=str(subject),
        email=str(email),
        full_name=str(profile.get("name") or email),
    )
