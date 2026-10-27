"""Column types that encrypt on the way in and decrypt on the way out.

The rest of the application keeps working with plain Python values; only the
database ever holds ciphertext. The consequence is that the database can no
longer compare, search or sort these columns, so code never does -- it filters
and sorts after loading, and looks accounts up by the keyed email index.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import LargeBinary, String, Text
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from .. import crypto

# Where long text can be long: schedule edits in the audit log.
LargeText = Text().with_variant(LONGTEXT(), "mysql")
PayloadBlob = LargeBinary().with_variant(LONGBLOB(), "mysql")


class EncryptedText(TypeDecorator[str]):
    """Free text: names, notes, reasons. ``context`` is the column's own name."""

    impl = Text
    cache_ok = True

    def __init__(self, context: str) -> None:
        self.context = context
        super().__init__()

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else crypto.seal_text(value, self.context)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else crypto.open_text(value, self.context)


class EncryptedString(TypeDecorator[str]):
    """Short text that is also unique, so it keeps a bounded length.

    The length leaves room for the ciphertext: base64 grows the value by a third,
    plus the nonce, the tag and the key id.
    """

    impl = String
    cache_ok = True

    def __init__(self, context: str, length: int) -> None:
        self.context = context
        self.length = length
        super().__init__(length=length)

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else crypto.seal_text(value, self.context)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else crypto.open_text(value, self.context)


class EncryptedJSON(TypeDecorator[Any]):
    """A JSON document stored as encrypted text."""

    impl = LargeText
    cache_ok = True

    def __init__(self, context: str) -> None:
        self.context = context
        super().__init__()

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else crypto.seal_json(value, self.context)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        return None if value is None else crypto.open_json(value, self.context)


class EncryptedBlob(TypeDecorator[bytes]):
    """Binary data: the compressed schedule."""

    impl = PayloadBlob
    cache_ok = True

    def __init__(self, context: str) -> None:
        self.context = context
        super().__init__()

    def process_bind_param(self, value: bytes | None, dialect: Dialect) -> bytes | None:
        return None if value is None else crypto.seal_bytes(bytes(value), self.context)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> bytes | None:
        return None if value is None else crypto.open_bytes(value, self.context)
