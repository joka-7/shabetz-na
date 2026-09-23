"""Export contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExportFormat(StrEnum):
    CSV = "csv"
    HTML = "html"
    PDF = "pdf"


@dataclass(frozen=True, slots=True)
class ExportedFile:
    content: bytes
    media_type: str
    filename: str


class ExporterUnavailable(RuntimeError):
    """A format is configured but its rendering backend is not installed."""
