"""Checking Firebase ID tokens.

A token is only proof of identity if every check holds: Google's signature,
this site's Firebase project as audience and issuer, and a time window. Each
test breaks exactly one of them.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from shabetz.auth.firebase import FirebaseAuthError, FirebaseVerifier

PROJECT = "shabetz-test"
NOW = 1_800_000_000


def make_key(kid: str = "key-1") -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": kid})


def claims(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": "firebase-uid-1",
        "iat": NOW - 10,
        "exp": NOW + 3600,
        "auth_time": NOW - 10,
        "email": "Dana@Example.com",
        "email_verified": True,
        "name": "Dana",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def sign(key: RSAKey, payload: dict[str, Any], alg: str = "RS256") -> str:
    return jwt.encode({"alg": alg, "kid": key.kid}, payload, key)


def verifier_for(*keys: RSAKey, calls: list[int] | None = None) -> FirebaseVerifier:
    def fetch() -> tuple[dict[str, Any], int]:
        if calls is not None:
            calls.append(1)
        return {"keys": [k.as_dict(private=False) for k in keys]}, 3600

    return FirebaseVerifier(PROJECT, fetch_keys=fetch, clock=lambda: NOW)


def test_a_valid_token_yields_the_identity() -> None:
    key = make_key()
    identity = verifier_for(key).verify(sign(key, claims()))
    assert identity.uid == "firebase-uid-1"
    assert identity.email == "dana@example.com"
    assert identity.email_verified is True
    assert identity.full_name == "Dana"


def test_a_token_signed_by_someone_else_is_refused() -> None:
    real, forged = make_key("key-1"), make_key("key-1")
    with pytest.raises(FirebaseAuthError):
        verifier_for(real).verify(sign(forged, claims()))


@pytest.mark.parametrize(
    "bad",
    [
        {"aud": "another-project"},
        {"iss": "https://securetoken.google.com/another-project"},
        {"exp": NOW - 3600},
        {"iat": NOW + 3600},
        {"sub": ""},
        {"auth_time": NOW + 3600},
        {"email": None},
    ],
    ids=[
        "audience",
        "issuer",
        "expired",
        "issued-in-future",
        "no-subject",
        "future-auth",
        "no-email",
    ],
)
def test_each_claim_is_checked(bad: dict[str, Any]) -> None:
    key = make_key()
    with pytest.raises(FirebaseAuthError):
        verifier_for(key).verify(sign(key, claims(**bad)))


def test_an_unsigned_token_is_refused() -> None:
    key = make_key()
    token = sign(key, claims())
    header, payload, _ = token.split(".")
    with pytest.raises(FirebaseAuthError):
        verifier_for(key).verify(f"{header}.{payload}.")


def test_garbage_is_refused() -> None:
    with pytest.raises(FirebaseAuthError):
        verifier_for(make_key()).verify("not a token")


def test_keys_are_cached_and_refetched_when_google_rotates_them() -> None:
    old, new = make_key("old"), make_key("new")
    calls: list[int] = []
    current = [old]

    def fetch() -> tuple[dict[str, Any], int]:
        calls.append(1)
        return {"keys": [k.as_dict(private=False) for k in current]}, 3600

    verifier = FirebaseVerifier(PROJECT, fetch_keys=fetch, clock=lambda: NOW)
    verifier.verify(sign(old, claims()))
    verifier.verify(sign(old, claims()))
    assert len(calls) == 1

    current.append(new)
    verifier.verify(sign(new, claims()))
    assert len(calls) == 2


def test_unverified_addresses_are_reported_as_such() -> None:
    key = make_key()
    identity = verifier_for(key).verify(sign(key, claims(email_verified=False)))
    assert identity.email_verified is False


def test_the_real_clock_is_the_default() -> None:
    verifier = FirebaseVerifier(PROJECT, fetch_keys=lambda: ({"keys": []}, 1))
    assert abs(verifier._clock() - time.time()) < 5
