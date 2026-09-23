"""Getting back in to the desktop app after forgetting a password.

The desktop app has one administrator more often than not, and nobody else to
reset it for them. It also runs only on its owner's computer, with its data in
their own folder, so proving you can open a file in that folder is proving you
own the data. A reset therefore writes a one-time code to a file there; typing
the code back sets a new password.

This is never offered on a hosted server, where the person at the browser is
not the person at the machine.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# No 0/O or 1/I/L: the code is read from a file and typed by a person.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_FILE = "password-reset-code.txt"
TTL_SECONDS = 15 * 60
MAX_ATTEMPTS = 5


def _digest(code: str) -> bytes:
    normalised = code.strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalised.encode()).digest()


@dataclass
class _Pending:
    digest: bytes
    expires_at: float
    attempts_left: int


class RecoveryCodes:
    """At most one outstanding code: issuing another replaces it.

    A code expires after a quarter hour and is spent by its first correct use
    or its fifth wrong one, so it cannot be guessed at any practical rate.
    """

    def __init__(
        self,
        ttl_seconds: int = TTL_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts
        self._clock = clock
        self._pending: _Pending | None = None

    def issue(self) -> str:
        chars = "".join(secrets.choice(ALPHABET) for _ in range(12))
        code = "-".join(chars[i : i + 4] for i in range(0, 12, 4))
        self._pending = _Pending(_digest(code), self._clock() + self._ttl, self._max_attempts)
        return code

    def redeem(self, supplied: str) -> bool:
        pending = self._pending
        if pending is None or self._clock() > pending.expires_at:
            self._pending = None
            return False
        if hmac.compare_digest(pending.digest, _digest(supplied)):
            self._pending = None
            return True
        pending.attempts_left -= 1
        if pending.attempts_left <= 0:
            self._pending = None
        return False


def write_code_file(directory: Path, code: str, emails: list[str]) -> Path:
    """Write the code, with instructions in both interface languages."""
    accounts = "\n".join(f"  {email}" for email in emails) or "  -"
    minutes = TTL_SECONDS // 60
    text = (
        f"Shabetz — password reset code\n"
        f"\n"
        f"    {code}\n"
        f"\n"
        f"Type this code into the Shabetz sign-in window with a new password.\n"
        f"It works once, for {minutes} minutes. If you did not ask for it, ignore it.\n"
        f"\n"
        f"Administrator accounts on this computer:\n{accounts}\n"
        f"\n"
        f"שבצ״נ — קוד לאיפוס סיסמה\n"
        f"\n"
        f"    {code}\n"
        f"\n"
        f"הקלידו את הקוד בחלון הכניסה של שבצ״נ, יחד עם סיסמה חדשה.\n"
        f"הקוד עובד פעם אחת, במשך {minutes} דקות. אם לא ביקשתם אותו, התעלמו ממנו.\n"
    )
    path = directory / CODE_FILE
    # UTF-8 with a byte order mark, so Notepad shows the Hebrew correctly.
    path.write_text(text, encoding="utf-8-sig")
    return path


def open_for_user(path: Path) -> None:
    """Open the file on this computer's screen, when that is possible.

    Best effort: the file path is also shown in the app, so failing to open it
    only costs the person a trip to File Explorer.
    """
    if sys.platform == "win32":
        with contextlib.suppress(OSError):
            os.startfile(path)  # type: ignore[attr-defined]


def remove_code_file(directory: Path) -> None:
    with contextlib.suppress(OSError):
        (directory / CODE_FILE).unlink()
