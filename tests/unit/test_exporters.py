"""Export rendering."""

from __future__ import annotations

import csv
import io

from shabetz.exporters.base import ExportFormat
from shabetz.exporters.renderers import (
    available_formats,
    pdf_engine_available,
    render,
    render_csv,
    render_html,
)

PAYLOAD = {
    "assignments": [
        {
            "person_id": 2, "person_name": "Rivka Shalev", "division_id": 1,
            "job_id": 1, "job_name": "Night watch", "template_id": 3,
            "template_name": "Evening", "calendar_date": "2026-10-01",
            "start_abs": 16.0, "end_abs": 24.0, "role": "MEMBER",
            "is_division_fallback": True, "satisfied_requirement_id": None,
        },
        {
            "person_id": 1, "person_name": "Yosef Mizrahi", "division_id": 1,
            "job_id": 1, "job_name": "Night watch", "template_id": 1,
            "template_name": "Overnight", "calendar_date": "2026-10-01",
            "start_abs": 22.0, "end_abs": 30.0, "role": "ROLE",
            "is_division_fallback": False, "satisfied_requirement_id": 1,
        },
    ],
    "warnings": [
        {"kind": "UNDERSTAFFED", "severity": "ERROR", "message": "Short by two"}
    ],
}
PARAMS = {"start_date": "2026-10-01", "end_date": "2026-10-07", "rest_period_hours": 8.0}
SUMMARY = {
    "total_assignments": 2, "total_people": 4, "people_used": 2,
    "utilization_rate": 0.5, "understaffed_shift_count": 1,
    "division_fallback_count": 1,
}


def test_csv_has_stable_columns_and_clock_times() -> None:
    out = render_csv(PAYLOAD, PARAMS, SUMMARY, "abcdef1234")
    text = out.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    assert out.filename == "shabetz-schedule_2026-10-01_2026-10-07_abcdef12.csv"
    assert rows[0]["clock_start"] == "16:00"
    assert rows[0]["clock_end"] == "00:00"
    # An overnight window wraps to a clock time rather than showing hour 30.
    assert rows[1]["clock_start"] == "22:00"
    assert rows[1]["clock_end"] == "06:00"


def test_csv_is_sorted_by_date_then_start() -> None:
    rows = list(
        csv.DictReader(
            io.StringIO(render_csv(PAYLOAD, PARAMS, SUMMARY, "x" * 10).content.decode("utf-8-sig"))
        )
    )
    assert [r["clock_start"] for r in rows] == ["16:00", "22:00"]


def test_csv_carries_a_bom_so_excel_reads_utf8() -> None:
    assert render_csv(PAYLOAD, PARAMS, SUMMARY, "x" * 10).content.startswith(b"\xef\xbb\xbf")


def test_html_includes_rows_warnings_and_repeating_header() -> None:
    html = render_html(PAYLOAD, PARAMS, SUMMARY, "abcdef1234").content.decode("utf-8")
    assert "Yosef Mizrahi" in html
    assert "Short by two" in html
    assert "table-header-group" in html, "print header must repeat across pages"
    assert "borrowed" in html


def test_html_escapes_names() -> None:
    payload = {
        "assignments": [
            {**PAYLOAD["assignments"][0], "person_name": "<script>alert(1)</script>"}
        ],
        "warnings": [],
    }
    html = render_html(payload, PARAMS, SUMMARY, "x" * 10).content.decode("utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_available_formats_always_include_csv_and_html() -> None:
    formats = available_formats()
    assert ExportFormat.CSV in formats
    assert ExportFormat.HTML in formats
    assert (ExportFormat.PDF in formats) is pdf_engine_available()


def test_render_dispatches_by_format() -> None:
    assert render(ExportFormat.CSV, PAYLOAD, PARAMS, SUMMARY, "x" * 10).media_type.startswith(
        "text/csv"
    )
    assert render(ExportFormat.HTML, PAYLOAD, PARAMS, SUMMARY, "x" * 10).media_type.startswith(
        "text/html"
    )
