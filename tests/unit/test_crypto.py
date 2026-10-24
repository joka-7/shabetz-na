"""Encryption of personal data at rest: the primitives."""

from __future__ import annotations

import pytest

from shabetz import crypto
from shabetz.crypto import Cipher, DataKeyError

KEY = "a-long-secret-for-the-tests-0123456789"
OTHER = "a-different-long-secret-for-tests-0123456789"


@pytest.fixture(autouse=True)
def _reset_crypto():  # type: ignore[no-untyped-def]
    crypto.configure(None)
    yield
    crypto.configure(None)


def test_text_and_bytes_round_trip_and_are_never_stored_in_the_clear() -> None:
    cipher = Cipher(KEY)
    sealed = cipher.seal_text("Dana Levi", "people.full_name")
    assert sealed.startswith("enc1:") and "Dana" not in sealed
    assert cipher.open_text(sealed, "people.full_name") == "Dana Levi"
    # A fresh nonce each time: the same name never looks the same twice.
    assert cipher.seal_text("Dana Levi", "people.full_name") != sealed

    blob = cipher.seal_bytes(b"\x1f\x8bschedule", "schedule_runs.payload_gz")
    assert blob.startswith(b"ENC1") and b"schedule" not in blob
    assert cipher.open_bytes(blob, "schedule_runs.payload_gz") == b"\x1f\x8bschedule"


def test_a_value_moved_to_another_column_does_not_open() -> None:
    cipher = Cipher(KEY)
    sealed = cipher.seal_text("secret", "time_off.reason")
    with pytest.raises(DataKeyError, match="integrity"):
        cipher.open_text(sealed, "people.full_name")


def test_tampering_is_detected() -> None:
    cipher = Cipher(KEY)
    sealed = cipher.seal_text("secret", "time_off.reason")
    flipped = sealed[:-2] + ("A" if sealed[-2] != "A" else "B") + sealed[-1]
    with pytest.raises(DataKeyError):
        cipher.open_text(flipped, "time_off.reason")
    blob = bytearray(cipher.seal_bytes(b"payload", "x"))
    blob[-1] ^= 1
    with pytest.raises(DataKeyError):
        cipher.open_bytes(bytes(blob), "x")


def test_the_wrong_key_cannot_read_and_says_which_key_is_missing() -> None:
    sealed = Cipher(KEY).seal_text("secret", "c")
    with pytest.raises(DataKeyError, match="SHABETZ_OLD_DATA_KEYS"):
        Cipher(OTHER).open_text(sealed, "c")


def test_old_keys_still_read_while_new_writes_use_the_newest() -> None:
    old = Cipher(KEY).seal_text("secret", "c")
    rotated = Cipher(OTHER, old=[KEY])
    assert rotated.open_text(old, "c") == "secret"
    fresh = rotated.seal_text("secret", "c")
    assert rotated.is_sealed_by_current_key(fresh)
    assert not rotated.is_sealed_by_current_key(old)
    assert Cipher(OTHER).open_text(fresh, "c") == "secret"


def test_a_short_key_is_refused() -> None:
    with pytest.raises(DataKeyError, match="at least 32"):
        Cipher("too-short")


def test_the_email_fingerprint_ignores_case_and_depends_on_the_key() -> None:
    a, b = Cipher(KEY), Cipher(OTHER)
    assert a.email_hash("Dana@Example.com ") == a.email_hash("dana@example.com")
    assert a.email_hash("dana@example.com") != b.email_hash("dana@example.com")
    assert len(a.email_hash("x@y.z")) == 64


def test_without_a_key_values_pass_through_and_legacy_plaintext_reads_back() -> None:
    assert crypto.seal_text("Dana", "c") == "Dana"
    assert crypto.open_text("Dana", "c") == "Dana"
    assert crypto.seal_bytes(b"abc", "c") == b"abc"
    assert crypto.open_bytes(b"abc", "c") == b"abc"


def test_text_that_looks_like_ciphertext_cannot_break_reading() -> None:
    # A name typed to resemble a sealed value, with no key configured, must come
    # back exactly as typed rather than being mistaken for ciphertext.
    for tricky in ("enc1:abcdefgh:AAAA", "​starts with the marker", "enc1:"):
        assert crypto.open_text(crypto.seal_text(tricky, "c"), "c") == tricky
    crypto.configure(KEY)
    for tricky in ("enc1:abcdefgh:AAAA", "​starts with the marker"):
        assert crypto.open_text(crypto.seal_text(tricky, "c"), "c") == tricky


def test_encrypted_data_without_a_key_says_so() -> None:
    crypto.configure(KEY)
    sealed = crypto.seal_text("secret", "c")
    crypto.configure(None)
    with pytest.raises(DataKeyError, match="SHABETZ_DATA_KEY"):
        crypto.open_text(sealed, "c")


def test_json_round_trips() -> None:
    crypto.configure(KEY)
    stored = crypto.seal_json({"person_name": "Dana", "n": [1, 2]}, "audit_log.before_json")
    assert "Dana" not in stored
    assert crypto.open_json(stored, "audit_log.before_json") == {"person_name": "Dana", "n": [1, 2]}
    # Rows from before encryption are plain JSON text.
    assert crypto.open_json('{"a": 1}', "audit_log.before_json") == {"a": 1}


def test_writing_plaintext_still_reads_the_key() -> None:
    crypto.configure(KEY)
    sealed = crypto.seal_text("Dana", "c")
    with crypto.writing_plaintext():
        assert crypto.seal_text("Dana", "c") == "Dana"
        assert crypto.open_text(sealed, "c") == "Dana"
    assert crypto.seal_text("Dana", "c").startswith("enc1:")
