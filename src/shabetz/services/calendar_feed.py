"""A person's published shifts as an iCalendar feed (RFC 5545).

Google Calendar, Apple Calendar and Outlook subscribe to an address and
refetch it every few hours, so a published change reaches people's phones
without them opening the app.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta

from .settings_service import zone

PRODID = "-//Shabetz//Shift schedule//EN"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Split a content line into pieces of at most 75 octets, as the format requires."""
    pieces: list[str] = []
    current = ""
    for char in line:
        limit = 75 if not pieces else 74  # continuation lines start with a space
        if len((current + char).encode()) > limit:
            pieces.append(current)
            current = char
        else:
            current += char
    pieces.append(current)
    return [pieces[0], *(" " + p for p in pieces[1:])]


def _utc(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def render_ics(
    *,
    calendar_name: str,
    schedule_start: date,
    time_zone: str,
    assignments: Iterable[dict],
    generated_at: datetime,
) -> str:
    """One event per shift; times are hours from the schedule's first midnight."""
    tz = zone(time_zone)
    origin = datetime(schedule_start.year, schedule_start.month, schedule_start.day)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        f"X-WR-TIMEZONE:{time_zone}",
    ]
    for a in assignments:
        # Wall-clock hours in the organisation's zone, then to UTC: a calendar
        # shows them right wherever the phone is.
        start = (origin + timedelta(hours=float(a["start_abs"]))).replace(tzinfo=tz)
        end = (origin + timedelta(hours=float(a["end_abs"]))).replace(tzinfo=tz)
        # Stable across republishing, so a calendar updates a shift in place
        # rather than showing it twice.
        uid = f"{a['job_id']}-{a['template_id']}-{a['calendar_date']}-{a['person_id']}@shabetz"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_utc(generated_at)}",
            f"DTSTART:{_utc(start.astimezone(zone('UTC')))}",
            f"DTEND:{_utc(end.astimezone(zone('UTC')))}",
            f"SUMMARY:{_escape(a['job_name'] + ' · ' + a['template_name'])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _fold(line)) + "\r\n"
