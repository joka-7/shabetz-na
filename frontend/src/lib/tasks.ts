/**
 * Turning "from 22:00 to 06:00" into a shift window and back. A task's hours
 * are shift windows underneath; the form speaks in clock times so nobody has
 * to think in start-plus-length.
 */

import type { ShiftTemplate } from "@/types/api";

export interface HoursRange {
  from: string;
  to: string;
}

export interface Window {
  start_hour: number;
  duration_hours: number;
}

const CLOCK = /^(\d{1,2}):(\d{2})$/;

function toHours(clock: string): number | null {
  const match = CLOCK.exec(clock.trim());
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  return h < 24 && m < 60 ? h + m / 60 : null;
}

/** The window for a pair of clock times; one that ends earlier crosses midnight. */
export function windowOf(range: HoursRange): Window | null {
  const start = toHours(range.from);
  const end = toHours(range.to);
  if (start === null || end === null || start === end) return null;
  const duration = end > start ? end - start : end + 24 - start;
  return { start_hour: start, duration_hours: Math.round(duration * 100) / 100 };
}

export function clock(hours: number): string {
  const minutes = Math.round(((hours % 24) + 24) % 24 * 60) % (24 * 60);
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

/** "06:00–14:00" for a window. */
export function windowLabel(w: Window): string {
  return `${clock(w.start_hour)}–${clock(w.start_hour + w.duration_hours)}`;
}

export function rangeOf(w: Window): HoursRange {
  return { from: clock(w.start_hour), to: clock(w.start_hour + w.duration_hours) };
}

export function crossesMidnight(w: Window): boolean {
  return w.start_hour + w.duration_hours > 24;
}

/** An existing shift window with exactly these hours, if there is one. */
export function matchingTemplate(templates: ShiftTemplate[], w: Window): ShiftTemplate | undefined {
  return templates.find(
    (t) =>
      t.is_active &&
      Math.abs(t.start_hour - w.start_hour) < 0.01 &&
      Math.abs(t.duration_hours - w.duration_hours) < 0.01,
  );
}

/** The distinct windows in a form, in the order given, and whether any row was unreadable. */
export function windowsOf(ranges: HoursRange[]): { windows: Window[]; invalid: boolean } {
  const windows: Window[] = [];
  let invalid = false;
  for (const range of ranges) {
    const w = windowOf(range);
    if (w === null) {
      invalid = true;
      continue;
    }
    if (!windows.some((x) => x.start_hour === w.start_hour && x.duration_hours === w.duration_hours)) {
      windows.push(w);
    }
  }
  return { windows, invalid };
}
