/** The schedule laid out as a wall chart: one table per week, a row per job window. */

import type { Assignment } from "@/types/api";

export interface GridRow {
  key: string;
  job: string;
  window: string;
  start: number;
  /** People per date. */
  cells: Record<string, string[]>;
}

export interface GridWeek {
  dates: string[];
  rows: GridRow[];
}

function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(y!, m! - 1, d! + days)).toISOString().slice(0, 10);
}

export function buildWeeks(assignments: Assignment[], from: string, to: string): GridWeek[] {
  const weeks: GridWeek[] = [];
  for (let start = from; start <= to; start = addDays(start, 7)) {
    const dates = Array.from({ length: 7 }, (_, i) => addDays(start, i)).filter((d) => d <= to);
    const inWeek = assignments.filter((a) => dates.includes(a.calendar_date));
    const rows = new Map<string, GridRow>();
    for (const a of inWeek) {
      const key = `${a.job_id}:${a.template_id}`;
      const row =
        rows.get(key) ??
        { key, job: a.job_name, window: a.template_name, start: a.start_abs % 24, cells: {} };
      (row.cells[a.calendar_date] ??= []).push(a.person_name);
      rows.set(key, row);
    }
    weeks.push({
      dates,
      rows: [...rows.values()].sort(
        (a, b) => a.job.localeCompare(b.job) || a.start - b.start,
      ),
    });
  }
  return weeks;
}
