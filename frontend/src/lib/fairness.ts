/** How evenly work is spread across people in a schedule. Pure, so testable. */

import type { Assignment, Person } from "@/types/api";

const HOURS_PER_DAY = 24;
// Friday and Saturday, the Israeli weekend (JS: 0 = Sunday).
const WEEKEND = new Set([5, 6]);

export interface FairnessRow {
  personId: number;
  name: string;
  divisionId: number;
  shifts: number;
  hours: number;
  nightShifts: number;
  weekendShifts: number;
}

/** True when any part of the shift falls between 22:00 and 06:00. */
export function isNightShift(start: number, end: number): boolean {
  const firstDay = Math.floor(start / HOURS_PER_DAY) - 1;
  const lastDay = Math.floor(end / HOURS_PER_DAY) + 1;
  for (let day = firstDay; day <= lastDay; day += 1) {
    const from = day * HOURS_PER_DAY - 2;
    const to = day * HOURS_PER_DAY + 6;
    if (start < to && end > from) return true;
  }
  return false;
}

/** A local calendar date's weekday; parsed by parts so no timezone shifts it. */
export function isWeekend(isoDate: string): boolean {
  const [y, m, d] = isoDate.split("-").map(Number);
  return WEEKEND.has(new Date(Date.UTC(y!, m! - 1, d)).getUTCDay());
}

export function fairnessRows(assignments: Assignment[], people: Person[]): FairnessRow[] {
  const rows = new Map<number, FairnessRow>();
  for (const person of people) {
    if (!person.is_active) continue;
    rows.set(person.id, {
      personId: person.id,
      name: person.full_name,
      divisionId: person.division_id,
      shifts: 0,
      hours: 0,
      nightShifts: 0,
      weekendShifts: 0,
    });
  }
  for (const a of assignments) {
    const row =
      rows.get(a.person_id) ??
      ({
        personId: a.person_id,
        name: a.person_name,
        divisionId: a.division_id,
        shifts: 0,
        hours: 0,
        nightShifts: 0,
        weekendShifts: 0,
      } satisfies FairnessRow);
    row.shifts += 1;
    row.hours += a.end_abs - a.start_abs;
    if (isNightShift(a.start_abs, a.end_abs)) row.nightShifts += 1;
    if (isWeekend(a.calendar_date)) row.weekendShifts += 1;
    rows.set(a.person_id, row);
  }
  return [...rows.values()].sort((a, b) => b.hours - a.hours || a.name.localeCompare(b.name));
}

/** Largest minus smallest value: a quick read on how uneven a column is. */
export function spread(values: number[]): number {
  return values.length ? Math.max(...values) - Math.min(...values) : 0;
}
