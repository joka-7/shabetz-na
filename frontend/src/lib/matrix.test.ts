import { describe, expect, it } from "vitest";
import { buildMatrix } from "./matrix";
import type { Assignment, ScheduleRun } from "@/types/api";

const shift = (person: number, date: string): Assignment => ({
  person_id: person,
  person_name: `P${person}`,
  division_id: 1,
  job_id: 1,
  job_name: "Desk",
  template_id: 7,
  template_name: "Night",
  calendar_date: date,
  start_abs: 24 + 23,
  end_abs: 24 + 31,
  role: "MEMBER",
  is_division_fallback: false,
  satisfied_requirement_id: null,
});

const run = (assignments: Assignment[], warnings: ScheduleRun["warnings"]): ScheduleRun =>
  ({
    schedule_id: "x",
    created_at: null,
    params: { start_date: "2026-10-05", end_date: "2026-10-07" },
    summary: {} as ScheduleRun["summary"],
    assignments,
    warnings,
  }) as ScheduleRun;

describe("buildMatrix", () => {
  it("has a column for every day, even days nobody works", () => {
    const m = buildMatrix(run([shift(1, "2026-10-05")], []));
    expect(m.dates).toEqual(["2026-10-05", "2026-10-06", "2026-10-07"]);
    expect(m.rows).toHaveLength(1);
    expect(m.rows[0]!.start).toBe(23);
    expect(m.rows[0]!.end).toBe(31);
  });

  it("turns an understaffed warning into empty places in that cell", () => {
    const m = buildMatrix(
      run([shift(1, "2026-10-05")], [
        {
          kind: "UNDERSTAFFED", severity: "ERROR", message: "", calendar_date: "2026-10-05",
          job_id: 1, template_id: 7, required: 3, assigned: 1,
        },
      ]),
    );
    expect(m.rows[0]!.cells["2026-10-05"]).toMatchObject({ missing: 2 });
    expect(m.rows[0]!.gaps).toBe(2);
  });

  it("keeps a row for a window nobody was assigned to, using the window's times", () => {
    const m = buildMatrix(
      run([], [
        {
          kind: "UNDERSTAFFED", severity: "ERROR", message: "", calendar_date: "2026-10-06",
          job_id: 2, template_id: 9, required: 1, assigned: 0, job_name: "Front desk", template_name: "Day",
        },
      ]),
      new Map([[9, { start_hour: 8, duration_hours: 8 }]]),
    );
    expect(m.rows).toHaveLength(1);
    expect(m.rows[0]).toMatchObject({ jobName: "Front desk", start: 8, end: 16, gaps: 1 });
  });
});
