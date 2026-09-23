"""Domain enums.

Note what is deliberately *absent* here: there is no ``Division`` enum and no
``SkillLevel`` enum.  Divisions, skills and proficiency levels are configured by
an administrator and live in the database as rows, so they can never be an enum
in code.  Only genuinely fixed vocabulary belongs in this module.
"""

from __future__ import annotations

from enum import StrEnum


class DivisionPolicy(StrEnum):
    """How a job may draw staff relative to the rotation's active division."""

    ACTIVE_DIVISION_ONLY = "ACTIVE_DIVISION_ONLY"
    ACTIVE_DIVISION_PREFERRED = "ACTIVE_DIVISION_PREFERRED"
    ANY_DIVISION = "ANY_DIVISION"


class AssignmentRole(StrEnum):
    """Why a person occupies a slot: to satisfy a named role, or as general fill."""

    ROLE = "ROLE"
    MEMBER = "MEMBER"


class WarningSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class WarningKind(StrEnum):
    UNDERSTAFFED = "UNDERSTAFFED"
    MISSING_ROLE = "MISSING_ROLE"
    DIVISION_FALLBACK = "DIVISION_FALLBACK"


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    SCHEDULER = "SCHEDULER"
    STAFF = "STAFF"


class TimeOffStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class FeasibilityVerdict(StrEnum):
    OK = "OK"
    TIGHT = "TIGHT"
    INFEASIBLE = "INFEASIBLE"
