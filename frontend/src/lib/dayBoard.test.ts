import { describe, expect, it } from "vitest";
import type { Assignment, Job } from "@/types/api";
import { buildDayBoard, scheduleDates, totalMissing } from "./dayBoard";

const a = (over: Partial<Assignment>): Assignment => ({
  person_id: 1,
  person_name: "Dana",
  division_id: 1,
  job_id: 1,
  job_name: "Patrol",
  template_id: 1,
  template_name: "Morning",
  calendar_date: "2026-10-12",
  start_abs: 6,
  end_abs: 14,
  role: "MEMBER",
  is_division_fallback: false,
  satisfied_requirement_id: null,
  ...over,
});

const job = (id: number, name: string, required: number): Job => ({
  id,
  name,
  required_people_per_shift: required,
  division_policy: "ACTIVE_DIVISION_PREFERRED",
  priority: null,
  is_active: true,
  shift_template_ids: [],
  requirements: [],
});

describe("buildDayBoard", () => {
  const assignments = [
    a({ person_id: 1, person_name: "Dana" }),
    a({ person_id: 2, person_name: "Avi" }),
    a({ person_id: 3, person_name: "Lee", job_id: 2, job_name: "Driver" }),
    a({ person_id: 4, person_name: "Noa", template_id: 2, template_name: "Night", start_abs: 22, end_abs: 30 }),
    a({ person_id: 5, person_name: "Other day", calendar_date: "2026-10-13" }),
  ];
  const jobs = [job(1, "Patrol", 3), job(2, "Driver", 1)];

  it("groups by shift in the order they start, then by task", () => {
    const board = buildDayBoard("2026-10-12", assignments, jobs);
    expect(board.map((s) => s.window)).toEqual(["Morning", "Night"]);
    expect(board[0]!.start).toBe("06:00");
    expect(board[0]!.end).toBe("14:00");
    expect(board[0]!.jobs.map((j) => j.job)).toEqual(["Driver", "Patrol"]);
    expect(board[0]!.jobs[1]!.people.map((p) => p.name)).toEqual(["Avi", "Dana"]);
  });

  it("ignores other days", () => {
    const board = buildDayBoard("2026-10-12", assignments, jobs);
    expect(JSON.stringify(board)).not.toContain("Other day");
  });

  it("counts how many are missing against what the task needs", () => {
    const board = buildDayBoard("2026-10-12", assignments, jobs);
    const patrol = board[0]!.jobs.find((j) => j.job === "Patrol")!;
    expect(patrol.required).toBe(3);
    expect(patrol.present).toBe(2);
    expect(patrol.missing).toBe(1);
  });

  it("does not count people who are away", () => {
    const board = buildDayBoard("2026-10-12", assignments, jobs, new Map([[1, "Leave"]]));
    const patrol = board[0]!.jobs.find((j) => j.job === "Patrol")!;
    expect(patrol.people.find((p) => p.id === 1)!.away).toBe("Leave");
    expect(patrol.present).toBe(1);
    expect(patrol.missing).toBe(2);
    // Two short on the morning patrol, and the night patrol (needs 3, has Noa) is two short too.
    expect(totalMissing(board)).toBe(4);
  });

  it("treats a task with no known requirement as fully staffed", () => {
    const board = buildDayBoard("2026-10-12", assignments, []);
    expect(board[0]!.jobs.every((j) => j.required === null && j.missing === 0)).toBe(true);
  });
});

describe("scheduleDates", () => {
  it("lists each date once, in order", () => {
    expect(scheduleDates([a({ calendar_date: "2026-10-13" }), a({}), a({})])).toEqual([
      "2026-10-12",
      "2026-10-13",
    ]);
  });
});
