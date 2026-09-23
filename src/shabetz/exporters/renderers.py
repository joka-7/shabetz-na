"""CSV, HTML and PDF renderers.

All three read the same run payload, and the PDF is produced from the HTML, so
there is a single template to keep correct.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .base import ExportedFile, ExporterUnavailable, ExportFormat

TEMPLATE_DIR = Path(__file__).parent / "templates"

CSV_COLUMNS = [
    "calendar_date",
    "template_name",
    "clock_start",
    "clock_end",
    "job_name",
    "person_name",
    "role",
    "division_id",
    "is_division_fallback",
]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        # Autoescape unconditionally rather than by file extension: the
        # template is named .html.j2, so extension-based detection would leave
        # escaping off and let a person's name inject markup into the report.
        autoescape=True,
    )


def _clock(hours: float) -> str:
    total = int(round(hours % 24 * 60))
    return f"{total // 60:02d}:{total % 60:02d}"


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for a in payload.get("assignments", []):
        rows.append(
            {
                **a,
                "clock_start": _clock(a["start_abs"]),
                "clock_end": _clock(a["end_abs"]),
            }
        )
    rows.sort(key=lambda r: (r["calendar_date"], r["start_abs"], r["job_name"], r["person_name"]))
    return rows


def _stem(params: dict[str, Any], schedule_id: str) -> str:
    return f"shabetz-schedule_{params.get('start_date')}_{params.get('end_date')}_{schedule_id[:8]}"


def render_csv(payload: dict, params: dict, summary: dict, schedule_id: str) -> ExportedFile:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in _rows(payload):
        writer.writerow(row)
    # A BOM so Excel opens non-ASCII names correctly instead of mojibake.
    content = buffer.getvalue().encode("utf-8-sig")
    return ExportedFile(content, "text/csv; charset=utf-8", f"{_stem(params, schedule_id)}.csv")


def render_html(payload: dict, params: dict, summary: dict, schedule_id: str) -> ExportedFile:
    html = (
        _env()
        .get_template("schedule.html.j2")
        .render(
            rows=_rows(payload),
            warnings=payload.get("warnings", []),
            params=params,
            summary=summary,
            schedule_id=schedule_id,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )
    )
    return ExportedFile(
        html.encode("utf-8"), "text/html; charset=utf-8", f"{_stem(params, schedule_id)}.html"
    )


def pdf_engine_available() -> bool:
    """Probe for WeasyPrint without importing it at module scope.

    WeasyPrint needs system Pango and cairo, and fails at *import* on slim
    images with an opaque OSError. Probing here keeps a missing system library
    from taking down the entire API at startup.
    """
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def render_pdf(payload: dict, params: dict, summary: dict, schedule_id: str) -> ExportedFile:
    if not pdf_engine_available():
        raise ExporterUnavailable(
            "PDF export needs WeasyPrint and its system libraries (pango, cairo). "
            "Install the 'pdf' extra and the system packages, or export CSV or HTML."
        )
    from weasyprint import HTML  # noqa: PLC0415

    html = render_html(payload, params, summary, schedule_id)
    pdf = HTML(string=html.content.decode("utf-8")).write_pdf()
    return ExportedFile(pdf, "application/pdf", f"{_stem(params, schedule_id)}.pdf")


RENDERERS = {
    ExportFormat.CSV: render_csv,
    ExportFormat.HTML: render_html,
    ExportFormat.PDF: render_pdf,
}


def available_formats() -> list[ExportFormat]:
    formats = [ExportFormat.CSV, ExportFormat.HTML]
    if pdf_engine_available():
        formats.append(ExportFormat.PDF)
    return formats


def render(
    fmt: ExportFormat, payload: dict, params: dict, summary: dict, schedule_id: str
) -> ExportedFile:
    return RENDERERS[fmt](payload, params, summary, schedule_id)
