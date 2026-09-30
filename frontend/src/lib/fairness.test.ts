import { describe, expect, it } from "vitest";
import { fairnessRows, isNightShift, isWeekend, spread } from "./fairness";
import type { Assignment, Person } from "@/types/api";

const person = (id: number, name: string): Person => ({
  id,
  full_name: name,
  division_id: 1,
  external_ref: null,
  is_active: true,
  working_weekdays: [],
  skills: [],
});

const shift = (personId: number, date: string, start: number, end: number): Assignment => ({
  person_id: personId,
  person_name: `P${personId}`,
  division_id: 1,
  job_id: 1,
  job_name: "Desk",
  template_id: 1,
  template_name: "W",
  calendar_date: date,
  start_abs: start,
  end_abs: end,
  role: "MEMBER",
  is_division_fallback: false,
  satisfied_requirement_id: null,
});

describe("fairness", () => {
  it("detects night shifts, including ones that cross midnight", () => {
    expect(isNightShift(8, 16)).toBe(false);
    expect(isNightShift(16, 24)).toBe(true); // runs to midnight
    expect(isNightShift(22, 30)).toBe(true);
    expect(isNightShift(30, 38)).toBe(false); // 06:00-14:00 next day
    expect(isNightShift(4, 12)).toBe(true); // early morning
  });

  it("detects the Friday/Saturday weekend", () => {
    expect(isWeekend("2026-10-09")).toBe(true); // Friday
    expect(isWeekend("2026-10-10")).toBe(true);
    expect(isWeekend("2026-10-11")).toBe(false); // Sunday
  });

  it("counts everyone, including people with no shifts", () => {
    const rows = fairnessRows(
      [shift(1, "2026-10-09", 8, 16), shift(1, "2026-10-10", 24 + 22, 24 + 30)],
      [person(1, "Ana"), person(2, "Ben")],
    );
    const ana = rows.find((r) => r.personId === 1)!;
    expect(ana).toMatchObject({ shifts: 2, hours: 16, nightShifts: 1, weekendShifts: 2 });
    expect(rows.find((r) => r.personId === 2)!.shifts).toBe(0);
    expect(spread(rows.map((r) => r.shifts))).toBe(2);
  });
});
