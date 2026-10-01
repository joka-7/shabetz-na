/** A month as weeks of days, and how many people are away on each. Pure, so testable. */

import type { TimeOff } from "@/types/api";

export interface CalendarDay {
  iso: string;
  day: number;
  inMonth: boolean;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

/**
 * `weekdayOrder` lists weekdays (Monday = 0 … Sunday = 6) in the order a week
 * is shown, so a Sunday-first week is [6, 0, 1, 2, 3, 4, 5].
 */
export function monthGrid(year: number, month: number, weekdayOrder: readonly number[]): CalendarDay[][] {
  const first = new Date(Date.UTC(year, month, 1));
  const firstWeekday = (first.getUTCDay() + 6) % 7; // Monday = 0
  const lead = (weekdayOrder.indexOf(firstWeekday) + 7) % 7;
  const start = new Date(Date.UTC(year, month, 1 - lead));
  const weeks: CalendarDay[][] = [];
  for (let w = 0; w < 6; w += 1) {
    const week: CalendarDay[] = [];
    for (let d = 0; d < 7; d += 1) {
      const day = new Date(start.getTime() + (w * 7 + d) * 86_400_000);
      week.push({ iso: iso(day), day: day.getUTCDate(), inMonth: day.getUTCMonth() === month });
    }
    // Drop a trailing week that is entirely the next month.
    if (w === 5 && !week.some((x) => x.inMonth)) break;
    weeks.push(week);
  }
  return weeks;
}

/** People away per day, counting requests that are still pending or already approved. */
export function awayByDay(requests: TimeOff[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const r of requests) {
    if (r.status !== "PENDING" && r.status !== "APPROVED") continue;
    for (let t = Date.parse(r.start_date); t <= Date.parse(r.end_date); t += 86_400_000) {
      const key = iso(new Date(t));
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return counts;
}

/** Inclusive number of days in a request. */
export function daysInRequest(r: Pick<TimeOff, "start_date" | "end_date">): number {
  return Math.round((Date.parse(r.end_date) - Date.parse(r.start_date)) / 86_400_000) + 1;
}
