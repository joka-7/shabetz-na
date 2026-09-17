"""Domain enums.

Note what is deliberately *absent* here: there is no ``Division`` enum and no
``SkillLevel`` enum.  Divisions, skills and proficiency levels are configured by
an administrator and live in the database as rows, so they can never be an enum
in code.  Only genuinely fixed vocabulary belongs in this module.
"""

from __future__ import annotations

from enum import Enum


class DivisionPolicy(str, Enum):
    """How a job may draw staff relative to the rotation's active division."""

    ACTIVE_DIVISION_ONLY = "ACTIVE_DIVISION_ONLY"
    ACTIVE_DIVISION_PREFERRED = "ACTIVE_DIVISION_PREFERRED"
    ANY_DIVISION = "ANY_DIVISION"


class AssignmentRole(str, Enum):
    """Why a person occupies a slot: to satisfy a named role, or as general fill."""

    ROLE = "ROLE"
    MEMBER = "MEMBER"


class WarningSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class WarningKind(str, Enum):
    UNDERSTAFFED = "UNDERSTAFFED"
    MISSING_ROLE = "MISSING_ROLE"
    DIVISION_FALLBACK = "DIVISION_FALLBACK"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    SCHEDULER = "SCHEDULER"
    STAFF = "STAFF"


class TimeOffStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class FeasibilityVerdict(str, Enum):
    OK = "OK"
    TIGHT = "TIGHT"
    INFEASIBLE = "INFEASIBLE"
