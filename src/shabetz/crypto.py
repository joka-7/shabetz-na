"""Encryption of personal data at rest.

What this is for: someone with access to the *database* -- a hosting provider's
staff, a leaked connection string, a stolen dump or backup -- should find
ciphertext where people's names, emails, notes and schedules would be. The key
lives in the application's environment (``SHABETZ_DATA_KEY``) and never in the
database.

What it is not for: the application itself has to read this data to work, so
whoever controls the application's environment, and therefore the key, can read
it too. Hiding it from them as well needs end-to-end encryption, which the
server cannot do for the user (docs/E2EE-DESIGN.md).

Design:
- AES-256-GCM, a fresh random nonce per value, and the column's name as
  authenticated data, so a value moved into another column fails to open.
- Subkeys are derived from the one secret with HKDF, one for the data and one
  for the email lookup index, so neither can stand in for the other.
- Every stored value says which key sealed it (``enc1:<key id>:...``). That is
  what lets keys be rotated: old keys stay listed for reading while new writes
  use the newest.
- Values written before encryption was switched on are still readable. Nothing
  is lost by turning it on, and ``shabetz encrypt-data`` finishes the job.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

TEXT_PREFIX = "enc1:"
BLOB_MAGIC = b"ENC1"
KEY_ID_LENGTH = 8
NONCE_LENGTH = 12
MIN_SECRET_LENGTH = 32
# A value that starts like ciphertext but was written in plain text is stored
# behind this marker, so it can never be mistaken for ciphertext when read.
ESCAPE = "​"


class DataKeyError(RuntimeError):
    """The key is missing, wrong, or the stored value has been tampered with."""


@dataclass(frozen=True)
class _Key:
    id: str
    data: bytes
    index: bytes


def _derive(secret: str) -> _Key:
    if len(secret) < MIN_SECRET_LENGTH:
        raise DataKeyError(
            f"The data key must be at least {MIN_SECRET_LENGTH} characters long "
            "(generate one with: shabetz generate-data-key)"
        )
    raw = secret.encode()

    def sub(info: bytes) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(raw)

    return _Key(
        id=hashlib.sha256(raw).hexdigest()[:KEY_ID_LENGTH],
        data=sub(b"shabetz data encryption v1"),
        index=sub(b"shabetz email index v1"),
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Cipher:
    """Seals and opens values with the newest key, reading with any listed key."""

    def __init__(self, current: str, old: Sequence[str] = ()) -> None:
        self._current = _derive(current)
        self._keys = {self._current.id: self._current}
        for secret in old:
            key = _derive(secret)
            self._keys.setdefault(key.id, key)

    @property
    def key_id(self) -> str:
        return self._current.id

    # ----------------------------------------------------------------- text

    def seal_text(self, value: str, context: str) -> str:
        nonce = os.urandom(NONCE_LENGTH)
        sealed = AESGCM(self._current.data).encrypt(nonce, value.encode(), context.encode())
        return f"{TEXT_PREFIX}{self._current.id}:{_b64(nonce + sealed)}"

    def open_text(self, stored: str, context: str) -> str:
        try:
            _, key_id, body = stored.split(":", 2)
            raw = _unb64(body)
        except ValueError as exc:
            raise DataKeyError("A stored value is not valid ciphertext") from exc
        return self._open(key_id, raw[:NONCE_LENGTH], raw[NONCE_LENGTH:], context).decode()

    # ---------------------------------------------------------------- bytes

    def seal_bytes(self, value: bytes, context: str) -> bytes:
        nonce = os.urandom(NONCE_LENGTH)
        sealed = AESGCM(self._current.data).encrypt(nonce, value, context.encode())
        return BLOB_MAGIC + self._current.id.encode() + nonce + sealed

    def open_bytes(self, stored: bytes, context: str) -> bytes:
        head = len(BLOB_MAGIC) + KEY_ID_LENGTH
        key_id = stored[len(BLOB_MAGIC) : head].decode(errors="replace")
        nonce = stored[head : head + NONCE_LENGTH]
        return self._open(key_id, nonce, stored[head + NONCE_LENGTH :], context)

    def _open(self, key_id: str, nonce: bytes, sealed: bytes, context: str) -> bytes:
        key = self._keys.get(key_id)
        if key is None:
            raise DataKeyError(
                f"Data was encrypted with a key (id {key_id}) that is not configured. "
                "Add it to SHABETZ_OLD_DATA_KEYS."
            )
        try:
            return AESGCM(key.data).decrypt(nonce, sealed, context.encode())
        except InvalidTag as exc:
            raise DataKeyError(
                "Stored data failed its integrity check: wrong key, or it was altered"
            ) from exc

    # ----------------------------------------------------------- email index

    def email_hash(self, email: str) -> str:
        """A keyed fingerprint of an address, so it can be looked up without being stored.

        Without the key it cannot be computed or reversed by guessing addresses,
        which an unkeyed hash of an email would allow.
        """
        digest = hmac.new(self._current.index, email.strip().lower().encode(), hashlib.sha256)
        return digest.hexdigest()

    def email_hashes(self, email: str) -> list[str]:
        """The fingerprint under every configured key, newest first.

        An account's fingerprint was made with whichever key was current when it
        was stored; looking under all of them keeps sign-in working while a key
        is being rotated.
        """
        wanted = email.strip().lower().encode()
        ordered = [self._current, *(k for k in self._keys.values() if k is not self._current)]
        return [hmac.new(k.index, wanted, hashlib.sha256).hexdigest() for k in ordered]

    def is_sealed_by_current_key(self, header: str | bytes) -> bool:
        """Whether a stored value's first bytes show it was sealed with the newest key."""
        if isinstance(header, bytes):
            return header.startswith(BLOB_MAGIC + self._current.id.encode())
        return header.startswith(f"{TEXT_PREFIX}{self._current.id}:")


# ------------------------------------------------------------------ the active cipher

_active: Cipher | None = None
# Off only while decrypting everything back to plain text: the key is still
# needed to read, but nothing new may be written encrypted.
_sealing = True


def configure(current: str | None, old: Sequence[str] = ()) -> Cipher | None:
    """Switch encryption on with this key, or off with ``None``. Returns the cipher."""
    global _active
    _active = Cipher(current, old) if current else None
    return _active


def configure_from_settings(settings: Any) -> Cipher | None:
    old = [part.strip() for part in settings.old_data_keys.split(",") if part.strip()]
    return configure(settings.data_key or None, old)


def active() -> Cipher | None:
    return _active


def sealing_cipher() -> Cipher | None:
    """The cipher new values are written with, or None when they are written plain."""
    return _active if _sealing else None


@contextmanager
def writing_plaintext() -> Iterator[None]:
    global _sealing
    previous, _sealing = _sealing, False
    try:
        yield
    finally:
        _sealing = previous


def generate_key() -> str:
    return _b64(os.urandom(32))


def is_sealed_text(value: object) -> bool:
    return isinstance(value, str) and value.startswith(TEXT_PREFIX)


def is_sealed_blob(value: object) -> bool:
    return isinstance(value, bytes | bytearray | memoryview) and bytes(value[:4]) == BLOB_MAGIC


def _need_cipher() -> Cipher:
    if _active is None:
        raise DataKeyError(
            "This data is encrypted but no key is configured. Set SHABETZ_DATA_KEY "
            "to the key it was encrypted with."
        )
    return _active


# ----------------------------------------------------- values as the database stores them


def seal_text(value: str, context: str) -> str:
    cipher = sealing_cipher()
    if cipher is not None:
        return cipher.seal_text(value, context)
    # Not encrypting. A value that merely looks like ciphertext, or like the
    # marker below, is stored behind the marker so it reads back unchanged.
    return ESCAPE + value if value.startswith((TEXT_PREFIX, ESCAPE)) else value


def open_text(stored: str, context: str) -> str:
    if stored.startswith(TEXT_PREFIX):
        return _need_cipher().open_text(stored, context)
    if stored.startswith(ESCAPE):
        return stored[len(ESCAPE) :]
    return stored


def seal_bytes(value: bytes, context: str) -> bytes:
    cipher = sealing_cipher()
    return cipher.seal_bytes(value, context) if cipher is not None else value


def open_bytes(stored: bytes, context: str) -> bytes:
    if bytes(stored[:4]) == BLOB_MAGIC:
        return _need_cipher().open_bytes(bytes(stored), context)
    return bytes(stored)


def seal_json(value: Any, context: str) -> str:
    return seal_text(json.dumps(value, separators=(",", ":")), context)


def open_json(stored: str, context: str) -> Any:
    if stored.startswith(TEXT_PREFIX):
        return json.loads(_need_cipher().open_text(stored, context))
    return json.loads(stored)
