"""Typed access to a project's scheduling settings."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from ..db.models import Project


class SchedulingSettings(BaseModel):
    """Scheduling knobs.

    There is deliberately no shifts-per-day cap: the rest window is the only
    limit on how often a person works.
    """

    rest_period_hours: float = 8.0
    rotation_enabled: bool = True
    rotation_block_days: int = 2
    rotation_anchor_date: date | None = None
    organization_name: str = ""
    timezone: str = "UTC"
    # Count each person's shifts in the four weeks before a new schedule, from
    # the published one, so whoever worked most lately is picked last.
    fairness_carry_over: bool = False
    setup_completed: bool = False


def zone(name: str) -> ZoneInfo:
    """The project's time zone, falling back to UTC for a name this machine lacks."""
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def project_today(settings: SchedulingSettings) -> date:
    """Today's date where the organisation is, not where the server is.

    A hosted server runs on UTC, which in Israel turns into tomorrow two or
    three hours early.
    """
    return datetime.now(zone(settings.timezone)).date()


def load_settings(db: DbSession, project_id: int) -> SchedulingSettings:
    project = db.get(Project, project_id)
    if project is None or not isinstance(project.settings_json, dict):
        return SchedulingSettings()
    return SchedulingSettings.model_validate(project.settings_json)


def save_settings(
    db: DbSession, project_id: int, settings: SchedulingSettings
) -> SchedulingSettings:
    project = db.get(Project, project_id)
    if project is None:
        raise LookupError(f"Project {project_id} does not exist")
    project.settings_json = settings.model_dump(mode="json")
    db.flush()
    return settings
