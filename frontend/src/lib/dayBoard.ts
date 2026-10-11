/**
 * One day of the schedule laid out by shift: for each shift window, each task
 * (job) with who works it and how many were needed. Shared by the by-shift
 * view, the shareable text and the status report, so they always agree.
 */

import { clockTime } from "@/lib/schedule";
import type { Assignment, Job } from "@/types/api";

export interface BoardPerson {
  id: number;
  name: string;
  /** Why they cannot be counted on today: leave, marked absent; null if fine. */
  away: string | null;
}

export interface BoardJob {
  jobId: number;
  job: string;
  /** How many the task needs; null when the task is unknown (removed). */
  required: number | null;
  people: BoardPerson[];
  /** People who can actually be counted on. */
  present: number;
  /** How many are still missing once those away are not counted. */
  missing: number;
}

export interface BoardShift {
  templateId: number;
  window: string;
  start: string;
  end: string;
  /** Sort key: hour of day the shift starts. */
  startHour: number;
  jobs: BoardJob[];
}

/** personId -> reason, for people who are away that day. An empty reason is allowed. */
export type AwayMap = Map<number, string>;

export function buildDayBoard(
  date: string,
  assignments: Assignment[],
  jobs: Job[],
  away: AwayMap = new Map(),
): BoardShift[] {
  const required = new Map(jobs.map((job) => [job.id, job.required_people_per_shift]));
  const shifts = new Map<number, BoardShift>();

  for (const a of assignments) {
    if (a.calendar_date !== date) continue;
    let shift = shifts.get(a.template_id);
    if (!shift) {
      shift = {
        templateId: a.template_id,
        window: a.template_name,
        start: clockTime(a.start_abs),
        end: clockTime(a.end_abs),
        startHour: ((a.start_abs % 24) + 24) % 24,
        jobs: [],
      };
      shifts.set(a.template_id, shift);
    }
    let job = shift.jobs.find((j) => j.jobId === a.job_id);
    if (!job) {
      job = {
        jobId: a.job_id,
        job: a.job_name,
        required: required.get(a.job_id) ?? null,
        people: [],
        present: 0,
        missing: 0,
      };
      shift.jobs.push(job);
    }
    job.people.push({
      id: a.person_id,
      name: a.person_name,
      away: away.has(a.person_id) ? away.get(a.person_id) ?? "" : null,
    });
  }

  for (const shift of shifts.values()) {
    for (const job of shift.jobs) {
      job.people.sort((x, y) => x.name.localeCompare(y.name));
      job.present = job.people.filter((p) => p.away === null).length;
      job.missing = job.required === null ? 0 : Math.max(0, job.required - job.present);
    }
    shift.jobs.sort((x, y) => x.job.localeCompare(y.job));
  }
  return [...shifts.values()].sort((x, y) => x.startHour - y.startHour);
}

/** Every date the schedule covers, in order. */
export function scheduleDates(assignments: Assignment[]): string[] {
  return [...new Set(assignments.map((a) => a.calendar_date))].sort();
}

/** Total people still missing across a day's shifts. */
export function totalMissing(board: BoardShift[]): number {
  return board.reduce((sum, shift) => sum + shift.jobs.reduce((s, j) => s + j.missing, 0), 0);
}
