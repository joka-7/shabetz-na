import type { Assignment } from "@/types/api";

/** Shifts grouped by calendar date, earliest first. */
export function groupByDate(assignments: Assignment[]): [string, Assignment[]][] {
  const byDate = new Map<string, Assignment[]>();
  for (const a of assignments) {
    const list = byDate.get(a.calendar_date) ?? [];
    list.push(a);
    byDate.set(a.calendar_date, list);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, list]) => [date, [...list].sort((x, y) => x.start_abs - y.start_abs)]);
}

/** The first shift that has not finished yet, by the viewer's local clock. */
export function nextShift(assignments: Assignment[], now: Date): Assignment | null {
  const pad = (n: number) => String(n).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const hour = now.getHours() + now.getMinutes() / 60;
  const candidates = assignments.filter((a) => {
    if (a.calendar_date > today) return true;
    if (a.calendar_date < today) return false;
    // Still running or yet to start: its end, counted from its own start of day.
    return (a.start_abs % 24) + (a.end_abs - a.start_abs) > hour;
  });
  candidates.sort(
    (a, b) => a.calendar_date.localeCompare(b.calendar_date) || a.start_abs - b.start_abs,
  );
  return candidates[0] ?? null;
}
