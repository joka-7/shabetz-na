/** Derived values for the dashboard. Pure functions, so they are testable. */

import type {
  Assignment,
  Division,
  ScheduleRun,
  ScheduleWarning,
} from "@/types/api";

const HOURS_PER_DAY = 24;

/** Absolute schedule hours rendered as a wall clock time. */
export function clockTime(absoluteHours: number): string {
  const minutes = Math.round(((absoluteHours % HOURS_PER_DAY) + HOURS_PER_DAY) % HOURS_PER_DAY * 60);
  const h = Math.floor(minutes / 60) % 24;
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function shiftWindow(assignment: Assignment): string {
  return `${clockTime(assignment.start_abs)}–${clockTime(assignment.end_abs)}`;
}

/** True when a shift finishes on a later calendar day. */
export function crossesMidnight(assignment: Assignment): boolean {
  const startDay = Math.floor(assignment.start_abs / HOURS_PER_DAY);
  const endDay = Math.ceil(assignment.end_abs / HOURS_PER_DAY) - 1;
  return endDay > startDay;
}

export function utilizationPercent(run: ScheduleRun): number {
  return Math.round(run.summary.utilization_rate * 100);
}

/**
 * Warnings an operator must act on.
 *
 * Division fallbacks are informational -- they record that the rotation was
 * relaxed to keep a shift staffed, which is not the same as a gap.
 */
export function blockingWarnings(warnings: ScheduleWarning[]): ScheduleWarning[] {
  return warnings.filter((w) => w.severity === "ERROR" || w.severity === "WARNING");
}

export function warningsBySeverity(
  warnings: ScheduleWarning[],
): Record<"ERROR" | "WARNING" | "INFO", number> {
  const counts = { ERROR: 0, WARNING: 0, INFO: 0 };
  for (const warning of warnings) counts[warning.severity] += 1;
  return counts;
}

export interface DayRotation {
  date: string;
  divisionId: number | null;
  divisionName: string;
}

export function rotationByDay(
  run: ScheduleRun,
  divisions: Division[],
): DayRotation[] {
  const names = new Map(divisions.map((d) => [d.id, d.name]));
  return Object.entries(run.summary.active_division_by_day)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, divisionId]) => ({
      date,
      divisionId,
      divisionName:
        divisionId === null ? "Rotation off" : (names.get(divisionId) ?? `Division ${divisionId}`),
    }));
}

export interface TimelineRow {
  date: string;
  templates: Map<number, Assignment[]>;
}

/** Group assignments into a date-by-window grid for the timeline view. */
export function buildTimeline(assignments: Assignment[]): TimelineRow[] {
  const byDate = new Map<string, Map<number, Assignment[]>>();
  for (const assignment of assignments) {
    let row = byDate.get(assignment.calendar_date);
    if (!row) {
      row = new Map();
      byDate.set(assignment.calendar_date, row);
    }
    const cell = row.get(assignment.template_id);
    if (cell) cell.push(assignment);
    else row.set(assignment.template_id, [assignment]);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, templates]) => ({ date, templates }));
}

export interface AssignmentFilters {
  search: string;
  divisionId: number | null;
  jobId: number | null;
  date: string | null;
}

export const emptyFilters: AssignmentFilters = {
  search: "",
  divisionId: null,
  jobId: null,
  date: null,
};

export function filterAssignments(
  assignments: Assignment[],
  filters: AssignmentFilters,
): Assignment[] {
  const needle = filters.search.trim().toLowerCase();
  return assignments.filter((a) => {
    if (filters.divisionId !== null && a.division_id !== filters.divisionId) return false;
    if (filters.jobId !== null && a.job_id !== filters.jobId) return false;
    if (filters.date !== null && a.calendar_date !== filters.date) return false;
    if (!needle) return true;
    return (
      a.person_name.toLowerCase().includes(needle) ||
      a.job_name.toLowerCase().includes(needle) ||
      a.template_name.toLowerCase().includes(needle)
    );
  });
}

/** Shifts per person, busiest first. */
export function shiftsPerPerson(
  assignments: Assignment[],
): { personId: number; personName: string; shifts: number }[] {
  const counts = new Map<number, { personName: string; shifts: number }>();
  for (const a of assignments) {
    const existing = counts.get(a.person_id);
    if (existing) existing.shifts += 1;
    else counts.set(a.person_id, { personName: a.person_name, shifts: 1 });
  }
  return [...counts.entries()]
    .map(([personId, v]) => ({ personId, ...v }))
    .sort((a, b) => b.shifts - a.shifts || a.personName.localeCompare(b.personName));
}
