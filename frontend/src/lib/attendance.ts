/**
 * Attendance for one day, and the status report built from it.
 *
 * A person counts as away when they are marked absent, or when they are on
 * approved leave and nobody has marked them present: an explicit "present"
 * wins, since people do come back early.
 */

import { totalMissing, type AwayMap, type BoardShift } from "@/lib/dayBoard";
import type { Absence } from "@/lib/share";
import type { AttendanceRow } from "@/types/api";

export interface AttendanceLabels {
  /** Used when someone is absent with no note. */
  absent: string;
  /** Used when someone is on leave with no stated reason. */
  leave: string;
}

export type Standing = "present" | "absent" | "leave" | "unmarked";

export function standing(row: AttendanceRow): Standing {
  if (row.status === "PRESENT") return "present";
  if (row.status === "ABSENT") return "absent";
  return row.on_leave ? "leave" : "unmarked";
}

export function awayMap(rows: AttendanceRow[], labels: AttendanceLabels): AwayMap {
  const away: AwayMap = new Map();
  for (const row of rows) {
    const s = standing(row);
    if (s === "absent") away.set(row.person_id, row.note || labels.absent);
    else if (s === "leave") away.set(row.person_id, row.leave_reason || labels.leave);
  }
  return away;
}

export function absencesOf(rows: AttendanceRow[], labels: AttendanceLabels): Absence[] {
  return rows
    .filter((row) => ["absent", "leave"].includes(standing(row)))
    .map((row) => ({
      name: row.full_name,
      note:
        standing(row) === "absent"
          ? row.note || labels.absent
          : row.leave_reason || labels.leave,
    }));
}

export interface AttendanceSummary {
  total: number;
  present: number;
  absent: number;
  leave: number;
  unmarked: number;
}

export function summarize(rows: AttendanceRow[]): AttendanceSummary {
  const counts = { total: rows.length, present: 0, absent: 0, leave: 0, unmarked: 0 };
  for (const row of rows) counts[standing(row)] += 1;
  return counts;
}

export interface ReportLabels {
  heading: (dateLabel: string) => string;
  totals: (s: AttendanceSummary) => string;
  absent: string;
  leave: string;
  unmarked: string;
  /** "Morning 06:00–14:00 · Patrol: 2 missing" */
  gap: (shift: string, job: string, missing: number) => string;
  gaps: string;
  allCovered: string;
}

/** The status report as a message: counts, who is away, who is unmarked, and what is short. */
export function reportText(
  dateLabel: string,
  rows: AttendanceRow[],
  board: BoardShift[],
  labels: ReportLabels,
): string {
  const lines = [`*${labels.heading(dateLabel)}*`, labels.totals(summarize(rows)), ""];

  const section = (title: string, items: string[]) => {
    if (items.length === 0) return;
    lines.push(`*${title}*`, ...items.map((item) => `• ${item}`), "");
  };
  section(
    labels.absent,
    rows
      .filter((r) => standing(r) === "absent")
      .map((r) => (r.note ? `${r.full_name} — ${r.note}` : r.full_name)),
  );
  section(
    labels.leave,
    rows
      .filter((r) => standing(r) === "leave")
      .map((r) => (r.leave_reason ? `${r.full_name} — ${r.leave_reason}` : r.full_name)),
  );
  section(
    labels.unmarked,
    rows.filter((r) => standing(r) === "unmarked").map((r) => r.full_name),
  );

  if (board.length > 0) {
    const gaps = board.flatMap((shift) =>
      shift.jobs
        .filter((job) => job.missing > 0)
        .map((job) =>
          labels.gap(`${shift.window} ${shift.start}–${shift.end}`, job.job, job.missing),
        ),
    );
    if (gaps.length > 0) section(labels.gaps, gaps);
    else if (totalMissing(board) === 0) lines.push(labels.allCovered);
  }
  return lines.join("\n").trimEnd();
}
