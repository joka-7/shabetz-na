/**
 * The schedule as a message that reads well pasted into WhatsApp (or anywhere
 * else): *bold* headings, one line per task, and who is away.
 */

import type { BoardShift } from "@/lib/dayBoard";

export interface Absence {
  name: string;
  note: string;
}

export interface ShareLabels {
  heading: (dateLabel: string) => string;
  /** Heading above the list of people who are away. */
  away: string;
  missing: (count: number) => string;
  noShifts: string;
}

export interface ShareDay {
  dateLabel: string;
  board: BoardShift[];
  absences: Absence[];
}

export function dayText(day: ShareDay, labels: ShareLabels): string {
  const lines: string[] = [`*${labels.heading(day.dateLabel)}*`, ""];

  if (day.board.length === 0) {
    lines.push(labels.noShifts);
  }
  for (const shift of day.board) {
    lines.push(`*${shift.window} ${shift.start}–${shift.end}*`);
    for (const job of shift.jobs) {
      const count = job.required === null ? `${job.present}` : `${job.present}/${job.required}`;
      // Someone away is struck through so it is clear they are named but not coming.
      const names = job.people.map((p) => (p.away === null ? p.name : `~${p.name}~`)).join(", ");
      const gap = job.missing > 0 ? ` ⚠️ ${labels.missing(job.missing)}` : "";
      lines.push(`• ${job.job} (${count}): ${names}${gap}`);
    }
    lines.push("");
  }

  if (day.absences.length > 0) {
    lines.push(`*${labels.away}*`);
    for (const absence of day.absences) {
      lines.push(absence.note ? `• ${absence.name} — ${absence.note}` : `• ${absence.name}`);
    }
  }
  return lines.join("\n").trimEnd();
}

export function daysText(days: ShareDay[], labels: ShareLabels): string {
  return days.map((day) => dayText(day, labels)).join("\n\n――――――――\n\n");
}

/** A link that opens WhatsApp with the text ready to send; null when too long for a link. */
export function whatsappLink(text: string): string | null {
  const url = `https://wa.me/?text=${encodeURIComponent(text)}`;
  return url.length <= 7000 ? url : null;
}
