import { describe, expect, it } from "vitest";
import {
  blockingWarnings,
  buildTimeline,
  clockTime,
  crossesMidnight,
  emptyFilters,
  filterAssignments,
  rotationByDay,
  shiftsPerPerson,
  utilizationPercent,
  warningsBySeverity,
} from "./schedule";
import type { Assignment, Division, ScheduleRun, ScheduleWarning } from "@/types/api";

function assignment(over: Partial<Assignment> = {}): Assignment {
  return {
    person_id: 1,
    person_name: "Dana Cohen",
    division_id: 1,
    job_id: 1,
    job_name: "Facility care",
    template_id: 1,
    template_name: "Window 1",
    calendar_date: "2026-10-01",
    start_abs: 0,
    end_abs: 8,
    role: "MEMBER",
    is_division_fallback: false,
    satisfied_requirement_id: null,
    ...over,
  };
}

describe("clockTime", () => {
  it("wraps absolute hours onto a 24 hour clock", () => {
    expect(clockTime(0)).toBe("00:00");
    expect(clockTime(8)).toBe("08:00");
    expect(clockTime(24)).toBe("00:00");
    // Hour 30 of the schedule is 06:00 the next morning, not "30:00".
    expect(clockTime(30)).toBe("06:00");
    expect(clockTime(8 + 24 * 5)).toBe("08:00");
  });

  it("renders half hours", () => {
    expect(clockTime(7.5)).toBe("07:30");
  });
});

describe("crossesMidnight", () => {
  it("is false for a window ending exactly at midnight", () => {
    expect(crossesMidnight(assignment({ start_abs: 16, end_abs: 24 }))).toBe(false);
  });

  it("is true for an overnight window", () => {
    expect(crossesMidnight(assignment({ start_abs: 22, end_abs: 30 }))).toBe(true);
  });
});

describe("warnings", () => {
  const warnings: ScheduleWarning[] = [
    { kind: "UNDERSTAFFED", severity: "ERROR", message: "a", calendar_date: null, job_id: null, template_id: null, required: null, assigned: null },
    { kind: "DIVISION_FALLBACK", severity: "INFO", message: "b", calendar_date: null, job_id: null, template_id: null, required: null, assigned: null },
    { kind: "MISSING_ROLE", severity: "WARNING", message: "c", calendar_date: null, job_id: null, template_id: null, required: null, assigned: null },
  ];

  it("treats division fallbacks as informational, not gaps", () => {
    expect(blockingWarnings(warnings)).toHaveLength(2);
  });

  it("counts by severity", () => {
    expect(warningsBySeverity(warnings)).toEqual({ ERROR: 1, WARNING: 1, INFO: 1 });
  });
});

describe("filterAssignments", () => {
  const rows = [
    assignment({ person_id: 1, person_name: "Dana Cohen", division_id: 1, job_id: 1 }),
    assignment({ person_id: 2, person_name: "Omri Levi", division_id: 2, job_id: 2, job_name: "Data entry" }),
    assignment({ person_id: 3, person_name: "Yael Barak", division_id: 1, job_id: 2, job_name: "Data entry", calendar_date: "2026-10-02" }),
  ];

  it("returns everything when no filter is set", () => {
    expect(filterAssignments(rows, emptyFilters)).toHaveLength(3);
  });

  it("filters by division, job and date", () => {
    expect(filterAssignments(rows, { ...emptyFilters, divisionId: 1 })).toHaveLength(2);
    expect(filterAssignments(rows, { ...emptyFilters, jobId: 2 })).toHaveLength(2);
    expect(filterAssignments(rows, { ...emptyFilters, date: "2026-10-02" })).toHaveLength(1);
  });

  it("searches person, job and window names case-insensitively", () => {
    expect(filterAssignments(rows, { ...emptyFilters, search: "omri" })).toHaveLength(1);
    expect(filterAssignments(rows, { ...emptyFilters, search: "DATA" })).toHaveLength(2);
  });

  it("combines filters conjunctively", () => {
    expect(
      filterAssignments(rows, { ...emptyFilters, divisionId: 1, jobId: 2 }),
    ).toHaveLength(1);
  });
});

describe("buildTimeline", () => {
  it("groups by date then window, in date order", () => {
    const rows = buildTimeline([
      assignment({ calendar_date: "2026-10-02", template_id: 1 }),
      assignment({ calendar_date: "2026-10-01", template_id: 1 }),
      assignment({ calendar_date: "2026-10-01", template_id: 2, person_id: 2 }),
    ]);
    expect(rows.map((r) => r.date)).toEqual(["2026-10-01", "2026-10-02"]);
    expect(rows[0]!.templates.size).toBe(2);
  });
});

describe("rotationByDay", () => {
  const divisions: Division[] = [
    { id: 1, name: "Division A", display_order: 0, color: null, is_active: true },
    { id: 2, name: "Division B", display_order: 1, color: null, is_active: true },
  ];

  it("names each day's active division in date order", () => {
    const run = {
      summary: {
        active_division_by_day: { "2026-10-02": 1, "2026-10-01": 1, "2026-10-03": 2 },
      },
    } as unknown as ScheduleRun;
    expect(rotationByDay(run, divisions).map((d) => [d.date, d.divisionName])).toEqual([
      ["2026-10-01", "Division A"],
      ["2026-10-02", "Division A"],
      ["2026-10-03", "Division B"],
    ]);
  });

  it("labels days with rotation disabled", () => {
    const run = {
      summary: { active_division_by_day: { "2026-10-01": null } },
    } as unknown as ScheduleRun;
    expect(rotationByDay(run, divisions)[0]!.divisionName).toBe("Rotation off");
  });
});

describe("utilizationPercent", () => {
  it("rounds the rate to a percentage", () => {
    expect(
      utilizationPercent({ summary: { utilization_rate: 0.666 } } as ScheduleRun),
    ).toBe(67);
  });
});

describe("shiftsPerPerson", () => {
  it("counts shifts and orders busiest first", () => {
    const result = shiftsPerPerson([
      assignment({ person_id: 1, person_name: "Dana" }),
      assignment({ person_id: 2, person_name: "Omri" }),
      assignment({ person_id: 1, person_name: "Dana" }),
    ]);
    expect(result[0]).toEqual({ personId: 1, personName: "Dana", shifts: 2 });
    expect(result[1]!.shifts).toBe(1);
  });
});
