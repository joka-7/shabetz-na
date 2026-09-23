"""Request and response models."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from ..domain.enums import (
    DivisionPolicy,
    FeasibilityVerdict,
    TimeOffStatus,
    UserRole,
)

ORM = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------- auth


class LoginRequest(BaseModel):
    email: str
    password: str


class BootstrapAdminRequest(BaseModel):
    email: str
    full_name: str
    password: str
    # Required on a server; the desktop app only listens locally and skips it.
    setup_code: str | None = None


class UserOut(BaseModel):
    model_config = ORM
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    person_id: int | None = None


class UserAdminOut(UserOut):
    """What an administrator sees when managing accounts.

    Carries whether each sign-in method is usable, so an invited account that
    cannot yet sign in is visible as such rather than looking ready.
    """

    has_password: bool = False
    has_google: bool = False
    last_login_at: datetime | None = None
    is_locked: bool = False


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=120)
    role: UserRole = UserRole.STAFF
    # Optional: an account may instead be reached through Google, or have its
    # password set later.
    password: str | None = None
    person_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    person_id: int | None = None


class PasswordSet(BaseModel):
    password: str


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


# -------------------------------------------------------------------- config


class DivisionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    display_order: int = 0
    color: str | None = None


class DivisionOut(DivisionIn):
    model_config = ORM
    id: int
    is_active: bool = True


class ProficiencyLevelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rank: int = Field(ge=0)


class ProficiencyLevelOut(ProficiencyLevelIn):
    model_config = ORM
    id: int
    is_active: bool = True


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class SkillOut(SkillIn):
    model_config = ORM
    id: int
    is_active: bool = True


class ShiftTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    start_hour: float = Field(ge=0, lt=24)
    duration_hours: float = Field(gt=0, le=24)
    color: str | None = None


class ShiftTemplateOut(ShiftTemplateIn):
    model_config = ORM
    id: int
    is_active: bool = True


class SplitDayRequest(BaseModel):
    """Generate evenly divided windows, the common case in the wizard."""

    shifts: int = Field(ge=1, le=24)
    start_hour: float = Field(default=0.0, ge=0, lt=24)
    total_hours: float = Field(default=24.0, gt=0, le=24)
    name_prefix: str = "Shift"


class RequirementIn(BaseModel):
    skill_id: int
    min_level_id: int
    required_count: int | None = Field(
        default=None,
        ge=1,
        description="None means every person on the shift; N means at least N do.",
    )
    is_leadership: bool = False


class RequirementOut(RequirementIn):
    model_config = ORM
    id: int
    skill_name: str | None = None


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    required_people_per_shift: int = Field(ge=1)
    division_policy: DivisionPolicy = DivisionPolicy.ACTIVE_DIVISION_PREFERRED
    priority: int | None = None
    shift_template_ids: list[int] = Field(default_factory=list)
    requirements: list[RequirementIn] = Field(default_factory=list)


class JobOut(BaseModel):
    model_config = ORM
    id: int
    name: str
    required_people_per_shift: int
    division_policy: DivisionPolicy
    priority: int | None
    is_active: bool
    shift_template_ids: list[int] = Field(default_factory=list)
    requirements: list[RequirementOut] = Field(default_factory=list)


class PersonSkillIn(BaseModel):
    skill_id: int
    level_id: int


class PersonIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    division_id: int
    external_ref: str | None = None
    working_weekdays: list[int] = Field(default_factory=list)
    skills: list[PersonSkillIn] = Field(default_factory=list)


class PersonOut(BaseModel):
    model_config = ORM
    id: int
    full_name: str
    division_id: int
    external_ref: str | None
    is_active: bool
    working_weekdays: list[int] = Field(default_factory=list)
    skills: list[PersonSkillIn] = Field(default_factory=list)


class SettingsIn(BaseModel):
    rest_period_hours: float = Field(default=8.0, ge=0, le=48)
    rotation_enabled: bool = True
    rotation_block_days: int = Field(default=2, ge=1, le=365)
    rotation_anchor_date: date | None = None
    organization_name: str = ""
    timezone: str = "UTC"
    week_start: int = Field(default=0, ge=0, le=6)


class SettingsOut(SettingsIn):
    setup_completed: bool = False


# --------------------------------------------------------------- feasibility


class WindowDemandOut(BaseModel):
    model_config = ORM
    template_id: int
    template_name: str
    start_hour: float
    duration_hours: float
    concurrent_people: int


class SkillFloorOut(BaseModel):
    model_config = ORM
    skill_id: int
    skill_name: str
    min_rank: int
    needed_distinct: int
    available: int
    satisfied: bool


class DivisionFeasibilityOut(BaseModel):
    model_config = ORM
    division_id: int
    division_name: str
    headcount: int
    expected_available: float
    minimum_distinct_needed: int
    verdict: FeasibilityVerdict
    messages: list[str] = Field(default_factory=list)
    skill_floors: list[SkillFloorOut] = Field(default_factory=list)


class FeasibilityOut(BaseModel):
    model_config = ORM
    verdict: FeasibilityVerdict
    person_shifts_per_day: int
    minimum_distinct_needed: int
    peak_concurrent_people: int
    window_demand: list[WindowDemandOut] = Field(default_factory=list)
    divisions: list[DivisionFeasibilityOut] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ schedule


class GenerateRequest(BaseModel):
    start_date: date
    end_date: date


class AssignmentOut(BaseModel):
    person_id: int
    person_name: str
    division_id: int
    job_id: int
    job_name: str
    template_id: int
    template_name: str
    calendar_date: date
    start_abs: float
    end_abs: float
    role: str
    is_division_fallback: bool
    satisfied_requirement_id: int | None = None


class WarningOut(BaseModel):
    kind: str
    severity: str
    message: str
    calendar_date: date | None = None
    job_id: int | None = None
    template_id: int | None = None
    required: int | None = None
    assigned: int | None = None


class SummaryOut(BaseModel):
    total_assignments: int
    total_people: int
    people_used: int
    utilization_rate: float
    understaffed_shift_count: int
    division_fallback_count: int
    active_division_by_day: dict[str, int | None] = Field(default_factory=dict)
    shifts_per_division: dict[int, int] = Field(default_factory=dict)


class ScheduleRunOut(BaseModel):
    schedule_id: str
    created_at: datetime | None = None
    params: dict = Field(default_factory=dict)
    summary: SummaryOut
    assignments: list[AssignmentOut] = Field(default_factory=list)
    warnings: list[WarningOut] = Field(default_factory=list)


class ScheduleRunSummaryOut(BaseModel):
    schedule_id: str
    created_at: datetime | None
    params: dict
    summary: SummaryOut


# ------------------------------------------------------------------ time off


class TimeOffIn(BaseModel):
    person_id: int | None = None
    start_date: date
    end_date: date
    reason: str | None = None


class TimeOffReview(BaseModel):
    note: str | None = None


class TimeOffOut(BaseModel):
    model_config = ORM
    id: int
    person_id: int
    start_date: date
    end_date: date
    reason: str | None
    status: TimeOffStatus
    review_note: str | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------- meta


class CapabilitiesOut(BaseModel):
    deployment: str = "server"
    setup_code_required: bool = False
    google_enabled: bool
    export_formats: list[str]
    pdf_available: bool
    setup_complete: bool
