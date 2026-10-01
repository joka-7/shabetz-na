import { describe, expect, it } from "vitest";
import { awayByDay, daysInRequest, monthGrid } from "./calendar";
import type { TimeOff } from "@/types/api";

const off = (start: string, end: string, status: TimeOff["status"]): TimeOff => ({
  id: 1, person_id: 1, start_date: start, end_date: end, reason: null, status, review_note: null, created_at: null,
});

describe("calendar", () => {
  it("lays a month out in weeks starting on the chosen day", () => {
    // October 2026 starts on a Thursday.
    const monday = monthGrid(2026, 9, [0, 1, 2, 3, 4, 5, 6]);
    expect(monday[0]![3]).toMatchObject({ iso: "2026-10-01", inMonth: true });
    expect(monday[0]![0]!.inMonth).toBe(false);
    const sunday = monthGrid(2026, 9, [6, 0, 1, 2, 3, 4, 5]);
    expect(sunday[0]![4]).toMatchObject({ iso: "2026-10-01" });
    expect(sunday.flat().every((d, i, all) => i === 0 || d.iso > all[i - 1]!.iso)).toBe(true);
  });

  it("counts people away, ignoring denied and cancelled requests", () => {
    const counts = awayByDay([
      off("2026-10-12", "2026-10-14", "APPROVED"),
      off("2026-10-13", "2026-10-13", "PENDING"),
      off("2026-10-13", "2026-10-13", "DENIED"),
    ]);
    expect(counts.get("2026-10-12")).toBe(1);
    expect(counts.get("2026-10-13")).toBe(2);
    expect(counts.get("2026-10-15")).toBeUndefined();
    expect(daysInRequest({ start_date: "2026-10-12", end_date: "2026-10-14" })).toBe(3);
  });
});
