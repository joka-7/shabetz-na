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

export type StartsIn =
  | { kind: "running" }
  | { kind: "later"; hours: number; minutes: number }
  | { kind: "day"; days: number };

/** How soon a shift starts, by the viewer's local clock. */
export function startsIn(a: Assignment, now: Date): StartsIn {
  const pad = (n: number) => String(n).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  if (a.calendar_date !== today) {
    const [y, m, d] = a.calendar_date.split("-").map(Number);
    const days = Math.round(
      (Date.UTC(y!, m! - 1, d!) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86_400_000,
    );
    return { kind: "day", days };
  }
  const nowHours = now.getHours() + now.getMinutes() / 60;
  const start = a.start_abs % 24;
  if (start <= nowHours) return { kind: "running" };
  const total = Math.round((start - nowHours) * 60);
  return { kind: "later", hours: Math.floor(total / 60), minutes: total % 60 };
}
