"""ORM models.

Every concept the original specification hardcoded lives here as a row:
divisions, shift templates, skills and the proficiency ladder are all
administrator-supplied data, never enum members.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..domain.enums import DivisionPolicy, TimeOffStatus, UserRole
from .base import TABLE_ARGS, Base, UtcDateTime, utcnow

# Bounded lengths for indexed or unique text columns; see db.base for why.
NAME_LEN = 120
LONG_NAME_LEN = 160
EMAIL_LEN = 255
TOKEN_LEN = 255


class User(Base):
    __tablename__ = "users"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(EMAIL_LEN), unique=True)
    # Either credential may be absent: an account can be password-only,
    # Google-only, or both once a Google identity is linked.
    password_hash: Mapped[str | None] = mapped_column(String(TOKEN_LEN), default=None)
    google_sub: Mapped[str | None] = mapped_column(
        String(TOKEN_LEN), unique=True, default=None
    )
    full_name: Mapped[str] = mapped_column(String(NAME_LEN))
    role: Mapped[UserRole] = mapped_column(String(32), default=UserRole.STAFF)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("people.id", ondelete="SET NULL"), default=None
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    person: Mapped[Person | None] = relationship(foreign_keys=[person_id])


class Session(Base):
    """Server-side sessions.

    Chosen over stateless tokens because a role change or a revocation must take
    effect on the very next request, which a self-contained token cannot offer.
    """

    __tablename__ = "sessions"
    __table_args__ = TABLE_ARGS

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    user_agent: Mapped[str | None] = mapped_column(String(TOKEN_LEN), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    user: Mapped[User] = relationship()


class Division(Base):
    __tablename__ = "divisions"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_LEN), unique=True)
    # This ordering *is* the rotation order, so there is one source of truth.
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str | None] = mapped_column(String(32), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProficiencyLevel(Base):
    """A rung on the administrator-defined proficiency ladder.

    Comparisons use ``rank``, never the name, so levels may be renamed,
    reordered, or extended to any depth without touching code.
    """

    __tablename__ = "proficiency_levels"
    __table_args__ = (UniqueConstraint("rank", name="uq_proficiency_levels_rank"), TABLE_ARGS)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    rank: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_LEN), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ShiftTemplate(Base):
    """A named working window; any start hour, any duration, any number."""

    __tablename__ = "shift_templates"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_LEN))
    start_hour: Mapped[float] = mapped_column(Float)
    duration_hours: Mapped[float] = mapped_column(Float)
    color: Mapped[str | None] = mapped_column(String(32), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(LONG_NAME_LEN))
    required_people_per_shift: Mapped[int] = mapped_column(Integer, default=1)
    division_policy: Mapped[DivisionPolicy] = mapped_column(
        String(40), default=DivisionPolicy.ACTIVE_DIVISION_PREFERRED
    )
    priority: Mapped[int | None] = mapped_column(Integer, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    shift_links: Mapped[list[JobShiftTemplate]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    requirements: Mapped[list[JobSkillRequirement]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobShiftTemplate(Base):
    __tablename__ = "job_shift_templates"
    __table_args__ = (
        UniqueConstraint("job_id", "shift_template_id", name="uq_job_shift_templates_job_id"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    shift_template_id: Mapped[int] = mapped_column(
        ForeignKey("shift_templates.id", ondelete="CASCADE")
    )

    job: Mapped[Job] = relationship(back_populates="shift_links")
    shift_template: Mapped[ShiftTemplate] = relationship()


class JobSkillRequirement(Base):
    """A staffing prerequisite.

    ``required_count`` of NULL means every person on the shift must meet it; an
    integer means at least that many must.  Expressing the mandatory leadership
    role this way, rather than as a dedicated column, lets a job demand several
    distinct roles at once.
    """

    __tablename__ = "job_skill_requirements"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"))
    min_level_id: Mapped[int] = mapped_column(
        ForeignKey("proficiency_levels.id", ondelete="RESTRICT")
    )
    required_count: Mapped[int | None] = mapped_column(Integer, default=None)
    is_leadership: Mapped[bool] = mapped_column(Boolean, default=False)

    job: Mapped[Job] = relationship(back_populates="requirements")
    skill: Mapped[Skill] = relationship()
    min_level: Mapped[ProficiencyLevel] = relationship()


class Person(Base):
    __tablename__ = "people"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_ref: Mapped[str | None] = mapped_column(String(NAME_LEN), default=None)
    full_name: Mapped[str] = mapped_column(String(LONG_NAME_LEN))
    division_id: Mapped[int] = mapped_column(ForeignKey("divisions.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    division: Mapped[Division] = relationship()
    skills: Mapped[list[PersonSkill]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    working_days: Mapped[list[PersonWorkingDay]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    time_off: Mapped[list[TimeOff]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
        foreign_keys="TimeOff.person_id",
    )


class PersonSkill(Base):
    __tablename__ = "person_skills"
    __table_args__ = (
        UniqueConstraint("person_id", "skill_id", name="uq_person_skills_person_id"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"))
    level_id: Mapped[int] = mapped_column(
        ForeignKey("proficiency_levels.id", ondelete="RESTRICT")
    )

    person: Mapped[Person] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship()
    level: Mapped[ProficiencyLevel] = relationship()


class PersonWorkingDay(Base):
    __tablename__ = "person_working_days"
    __table_args__ = (
        UniqueConstraint("person_id", "weekday", name="uq_person_working_days_person_id"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)

    person: Mapped[Person] = relationship(back_populates="working_days")


class TimeOff(Base):
    """Absence and its approval workflow in one table.

    Only APPROVED rows make a person unavailable, so a pending request never
    silently changes a schedule.  Keeping the request and the resulting absence
    as one row avoids two competing answers to "who is actually away".
    """

    __tablename__ = "time_off"
    __table_args__ = (
        Index("ix_time_off_person_dates", "person_id", "start_date", "end_date"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[TimeOffStatus] = mapped_column(String(20), default=TimeOffStatus.PENDING)
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    review_note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    person: Mapped[Person] = relationship(back_populates="time_off", foreign_keys=[person_id])


class Setting(Base):
    """Singleton configuration, one row per key."""

    __tablename__ = "settings"
    __table_args__ = TABLE_ARGS

    key: Mapped[str] = mapped_column(String(NAME_LEN), primary_key=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class ScheduleRun(Base):
    """A generated schedule, persisted so exports can be keyed by id.

    The original cached a dataframe in a module global, which meant a second
    worker process had no idea the schedule existed.  A row does not have that
    problem.
    """

    __tablename__ = "schedule_runs"
    __table_args__ = TABLE_ARGS

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    params_json: Mapped[dict] = mapped_column(JSON)
    summary_json: Mapped[dict] = mapped_column(JSON)
    payload_gz: Mapped[bytes] = mapped_column(LONGBLOB)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), default=None)
    action: Mapped[str] = mapped_column(String(32))
    before_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    after_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
