"""Coverage warnings for one shift slot.

Shared by the greedy engine and by manual edits, so a schedule that has been
hand-adjusted reports its gaps in exactly the words a freshly generated one does.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.enums import WarningKind, WarningSeverity
from ..domain.models import Assignment, Job, ScheduleWarning, ShiftSlot


def slot_warnings(job: Job, slot: ShiftSlot, picked: Sequence[Assignment]) -> list[ScheduleWarning]:
    warnings: list[ScheduleWarning] = []

    if len(picked) < job.required_people_per_shift:
        warnings.append(
            ScheduleWarning(
                kind=WarningKind.UNDERSTAFFED,
                severity=WarningSeverity.ERROR,
                message=(
                    f"{job.name} on {slot.calendar_date.isoformat()} "
                    f"({slot.template_name}) has {len(picked)} of "
                    f"{job.required_people_per_shift} required staff"
                ),
                calendar_date=slot.calendar_date,
                job_id=job.id,
                template_id=slot.template_id,
                required=job.required_people_per_shift,
                assigned=len(picked),
                job_name=job.name,
                template_name=slot.template_name,
            )
        )

    for requirement in job.role_requirements:
        filled = sum(1 for a in picked if a.satisfied_requirement_id == requirement.id)
        if filled < (requirement.required_count or 0):
            warnings.append(
                ScheduleWarning(
                    kind=WarningKind.MISSING_ROLE,
                    severity=WarningSeverity.ERROR,
                    message=(
                        f"{job.name} on {slot.calendar_date.isoformat()} "
                        f"({slot.template_name}) needs "
                        f"{requirement.required_count} x {requirement.skill_name} "
                        f"but filled {filled}"
                    ),
                    calendar_date=slot.calendar_date,
                    job_id=job.id,
                    template_id=slot.template_id,
                    required=requirement.required_count,
                    assigned=filled,
                    job_name=job.name,
                    template_name=slot.template_name,
                    skill_name=requirement.skill_name,
                )
            )

    for assignment in picked:
        if assignment.is_division_fallback:
            warnings.append(
                ScheduleWarning(
                    kind=WarningKind.DIVISION_FALLBACK,
                    severity=WarningSeverity.INFO,
                    message=(
                        f"{assignment.person_name} was borrowed from outside the "
                        f"active division for {job.name} on "
                        f"{slot.calendar_date.isoformat()}"
                    ),
                    calendar_date=slot.calendar_date,
                    job_id=job.id,
                    template_id=slot.template_id,
                    job_name=job.name,
                    template_name=slot.template_name,
                    person_name=assignment.person_name,
                )
            )

    return warnings
