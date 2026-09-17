"""Typed access to the singleton settings rows."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db.models import Setting


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


SETTINGS_KEY = "scheduling"


def load_settings(db: DbSession) -> SchedulingSettings:
    row = db.scalar(select(Setting).where(Setting.key == SETTINGS_KEY))
    if row is None or not isinstance(row.value_json, dict):
        return SchedulingSettings()
    return SchedulingSettings.model_validate(row.value_json)


def save_settings(db: DbSession, settings: SchedulingSettings) -> SchedulingSettings:
    payload: dict[str, Any] = settings.model_dump(mode="json")
    row = db.scalar(select(Setting).where(Setting.key == SETTINGS_KEY))
    if row is None:
        db.add(Setting(key=SETTINGS_KEY, value_json=payload))
    else:
        row.value_json = payload
    db.flush()
    return settings
