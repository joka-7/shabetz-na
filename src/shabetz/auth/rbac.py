"""Role capabilities.

Authorization is decided here and enforced by API dependencies.  The frontend
hides what a role cannot use; this is what actually refuses it.
"""

from __future__ import annotations

from ..domain.enums import UserRole

_RANK = {UserRole.STAFF: 0, UserRole.SCHEDULER: 1, UserRole.ADMIN: 2}


def at_least(role: UserRole, minimum: UserRole) -> bool:
    return _RANK[role] >= _RANK[minimum]


def can_edit_configuration(role: UserRole) -> bool:
    return role is UserRole.ADMIN


def can_manage_users(role: UserRole) -> bool:
    return role is UserRole.ADMIN


def can_generate_schedule(role: UserRole) -> bool:
    return at_least(role, UserRole.SCHEDULER)


def can_view_all_assignments(role: UserRole) -> bool:
    return at_least(role, UserRole.SCHEDULER)


def can_review_time_off(role: UserRole) -> bool:
    return at_least(role, UserRole.SCHEDULER)
