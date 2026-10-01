import { describe, expect, it } from "vitest";
import { groupByDate, nextShift } from "./myShifts";
import type { Assignment } from "@/types/api";

const shift = (date: string, start: number, end: number): Assignment => ({
  person_id: 1,
  person_name: "Ana",
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

describe("my shifts", () => {
  it("groups by date in order", () => {
    const groups = groupByDate([shift("2026-10-06", 32, 40), shift("2026-10-05", 16, 24), shift("2026-10-05", 8, 16)]);
    expect(groups.map(([d]) => d)).toEqual(["2026-10-05", "2026-10-06"]);
    expect(groups[0]![1].map((a) => a.start_abs)).toEqual([8, 16]);
  });

  it("finds the next unfinished shift", () => {
    const list = [shift("2026-10-05", 8, 16), shift("2026-10-05", 16, 24), shift("2026-10-06", 32, 40)];
    const at = (h: number) => new Date(2026, 9, 5, h, 0);
    expect(nextShift(list, at(9))).toBe(list[0]); // mid-shift still counts
    expect(nextShift(list, at(17))).toBe(list[1]);
    expect(nextShift(list, at(23.5))).toBe(list[1]);
    expect(nextShift(list, new Date(2026, 9, 6, 1, 0))).toBe(list[2]);
    expect(nextShift(list, new Date(2026, 9, 7, 1, 0))).toBeNull();
  });
});
