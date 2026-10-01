/** The schedule as rows (a job's window) by columns (days). Pure, so testable. */

import type { Assignment, ScheduleRun } from "@/types/api";

export interface MatrixCell {
  people: Assignment[];
  /** Places still empty after the people who were assigned. */
  missing: number;
}

export interface MatrixRow {
  key: string;
  jobId: number;
  templateId: number;
  jobName: string;
  templateName: string;
  /** Clock hours of the window's start and end. */
  start: number;
  end: number;
  cells: Record<string, MatrixCell>;
  gaps: number;
}

export interface Matrix {
  dates: string[];
  rows: MatrixRow[];
}

function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(y!, m! - 1, d! + days)).toISOString().slice(0, 10);
}

export interface WindowTimes {
  start_hour: number;
  duration_hours: number;
}

/**
 * `windows` (shift templates by id) supplies the times for a job window that
 * nobody was assigned to at all: it appears only in the warnings, and its gap
 * is exactly what should still be visible.
 */
export function buildMatrix(run: ScheduleRun, windows?: Map<number, WindowTimes>): Matrix {
  const from = String(run.params.start_date ?? "");
  const to = String(run.params.end_date ?? "");
  const dates: string[] = [];
  if (from && to) for (let d = from; d <= to; d = addDays(d, 1)) dates.push(d);

  const rows = new Map<string, MatrixRow>();
  const rowFor = (jobId: number, templateId: number, jobName: string, templateName: string, start: number, end: number) => {
    const key = `${jobId}:${templateId}`;
    let row = rows.get(key);
    if (!row) {
      row = { key, jobId, templateId, jobName, templateName, start: start % 24, end: start % 24 + (end - start), cells: {}, gaps: 0 };
      rows.set(key, row);
    }
    return row;
  };

  for (const a of run.assignments) {
    const row = rowFor(a.job_id, a.template_id, a.job_name, a.template_name, a.start_abs, a.end_abs);
    (row.cells[a.calendar_date] ??= { people: [], missing: 0 }).people.push(a);
  }

  // Gaps come from the schedule's own warnings, so a window with nobody at all
  // still gets a row and the right number of empty places.
  for (const w of run.warnings) {
    if (w.kind !== "UNDERSTAFFED" || w.job_id === null || w.template_id === null || !w.calendar_date) continue;
    const times = windows?.get(w.template_id);
    const row = rowFor(
      w.job_id,
      w.template_id,
      w.job_name ?? `#${w.job_id}`,
      w.template_name ?? `#${w.template_id}`,
      times?.start_hour ?? 0,
      (times?.start_hour ?? 0) + (times?.duration_hours ?? 0),
    );
    const missing = Math.max(0, (w.required ?? 0) - (w.assigned ?? 0));
    (row.cells[w.calendar_date] ??= { people: [], missing: 0 }).missing = missing;
    row.gaps += missing;
  }

  const sorted = [...rows.values()].sort(
    (a, b) => a.jobName.localeCompare(b.jobName) || a.start - b.start,
  );
  return { dates, rows: sorted };
}
