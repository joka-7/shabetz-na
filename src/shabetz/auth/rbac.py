"""Role capabilities within a project.

Authorization is decided here and enforced by API dependencies. The frontend
hides what a role cannot use; this is what actually refuses it.
"""

from __future__ import annotations

from ..domain.enums import ProjectRole

_RANK = {ProjectRole.STAFF: 0, ProjectRole.COLLABORATOR: 1, ProjectRole.ADMIN: 2}


def at_least(role: ProjectRole, minimum: ProjectRole) -> bool:
    return _RANK[role] >= _RANK[minimum]


def can_edit_configuration(role: ProjectRole) -> bool:
    return at_least(role, ProjectRole.COLLABORATOR)


def can_manage_members(role: ProjectRole) -> bool:
    return role is ProjectRole.ADMIN


def can_generate_schedule(role: ProjectRole) -> bool:
    return at_least(role, ProjectRole.COLLABORATOR)


def can_view_all_assignments(role: ProjectRole) -> bool:
    return at_least(role, ProjectRole.COLLABORATOR)


def can_review_time_off(role: ProjectRole) -> bool:
    return at_least(role, ProjectRole.COLLABORATOR)
