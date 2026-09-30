import { describe, expect, it } from "vitest";
import { buildWeeks } from "./printGrid";
import type { Assignment } from "@/types/api";

const shift = (name: string, date: string, template = 1): Assignment => ({
  person_id: 1,
  person_name: name,
  division_id: 1,
  job_id: 1,
  job_name: "Desk",
  template_id: template,
  template_name: template === 1 ? "Day" : "Night",
  calendar_date: date,
  start_abs: template === 1 ? 8 : 22,
  end_abs: 16,
  role: "MEMBER",
  is_division_fallback: false,
  satisfied_requirement_id: null,
});

describe("buildWeeks", () => {
  it("splits a range into weeks and groups people by job window and day", () => {
    const weeks = buildWeeks(
      [shift("Ana", "2026-10-05"), shift("Ben", "2026-10-05"), shift("Cat", "2026-10-12", 2)],
      "2026-10-05",
      "2026-10-13",
    );
    expect(weeks).toHaveLength(2);
    expect(weeks[0]!.dates).toHaveLength(7);
    expect(weeks[1]!.dates).toEqual(["2026-10-12", "2026-10-13"]);
    expect(weeks[0]!.rows[0]!.cells["2026-10-05"]).toEqual(["Ana", "Ben"]);
    expect(weeks[1]!.rows[0]!.window).toBe("Night");
  });
});
