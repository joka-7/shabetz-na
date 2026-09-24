"""Google sign-in through Firebase Authentication.

The browser signs in with Google in a Firebase popup and hands the server the
resulting ID token. That token is a JWT signed by Google; checking it here --
signature against Google's published keys, audience, issuer, expiry -- is what
makes it proof of identity rather than a claim the browser could invent.

No Firebase service account is needed: the public keys are enough to verify.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from joserfc import jws, jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

# Firebase ID tokens are signed with the securetoken service account's keys.
KEYS_URL = (
    "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
)
DEFAULT_KEYS_TTL_SECONDS = 3600
CLOCK_SKEW_SECONDS = 60


class FirebaseAuthError(Exception):
    """The token is not a valid sign-in for this Firebase project."""


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str
    email_verified: bool
    full_name: str


def _max_age(cache_control: str) -> int:
    for part in cache_control.split(","):
        name, _, value = part.strip().partition("=")
        if name == "max-age" and value.isdigit():
            return int(value)
    return DEFAULT_KEYS_TTL_SECONDS


def fetch_google_keys() -> tuple[dict[str, Any], int]:
    """Google's current signing keys, and how long they may be cached."""
    response = httpx.get(KEYS_URL, timeout=10.0)
    response.raise_for_status()
    return response.json(), _max_age(response.headers.get("cache-control", ""))


class FirebaseVerifier:
    """Verifies ID tokens for one Firebase project.

    Keys are cached for as long as Google says they may be, and refetched once
    early if a token names a key the cache does not hold -- that is what a key
    rotation looks like from here.
    """

    def __init__(
        self,
        project_id: str,
        fetch_keys: Callable[[], tuple[dict[str, Any], int]] = fetch_google_keys,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.project_id = project_id
        self._fetch_keys = fetch_keys
        self._clock = clock
        self._keys: KeySet | None = None
        self._kids: set[str] = set()
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _key_set(self, kid: str | None) -> KeySet:
        with self._lock:
            stale = self._keys is None or self._clock() >= self._expires_at
            if stale or (kid is not None and kid not in self._kids):
                try:
                    data, ttl = self._fetch_keys()
                    keys = KeySet.import_key_set(data)  # type: ignore[arg-type]
                except (httpx.HTTPError, ValueError, JoseError) as exc:
                    if self._keys is None:
                        raise FirebaseAuthError("Could not load Google's signing keys") from exc
                else:
                    self._keys = keys
                    self._kids = {str(k.kid) for k in keys.keys if k.kid}
                    self._expires_at = self._clock() + ttl
            assert self._keys is not None
            return self._keys

    def verify(self, id_token: str) -> FirebaseIdentity:
        try:
            header = jws.extract_compact(id_token.encode()).protected
        except (JoseError, ValueError) as exc:
            raise FirebaseAuthError("Malformed sign-in token") from exc
        kid = header.get("kid")

        try:
            token = jwt.decode(id_token, self._key_set(kid), algorithms=["RS256"])
        except (JoseError, ValueError) as exc:
            raise FirebaseAuthError("Sign-in token signature is not valid") from exc

        now = int(self._clock())
        registry = JWTClaimsRegistry(
            now=now,
            leeway=CLOCK_SKEW_SECONDS,
            iss={"essential": True, "value": f"https://securetoken.google.com/{self.project_id}"},
            aud={"essential": True, "value": self.project_id},
            sub={"essential": True},
            exp={"essential": True},
            iat={"essential": True},
        )
        try:
            registry.validate(token.claims)
        except JoseError as exc:
            raise FirebaseAuthError("Sign-in token is expired or not for this site") from exc

        claims = token.claims
        uid = str(claims.get("sub") or "")
        if not uid or len(uid) > 128:
            raise FirebaseAuthError("Sign-in token has no user")
        auth_time = claims.get("auth_time")
        if not isinstance(auth_time, int | float) or auth_time > now + CLOCK_SKEW_SECONDS:
            raise FirebaseAuthError("Sign-in token has no valid sign-in time")
        email = str(claims.get("email") or "").strip().lower()
        if not email:
            raise FirebaseAuthError("This Google account shares no email address")

        return FirebaseIdentity(
            uid=uid,
            email=email,
            email_verified=claims.get("email_verified") is True,
            full_name=str(claims.get("name") or email)[:120],
        )
