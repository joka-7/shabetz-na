"""Typed access to a project's scheduling settings."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
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
    week_start: int = Field(default=0, ge=0, le=6)
    setup_completed: bool = False


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
