import { describe, expect, it } from "vitest";
import type { ShiftTemplate } from "@/types/api";
import { clock, crossesMidnight, matchingTemplate, rangeOf, windowLabel, windowOf, windowsOf } from "./tasks";

const template = (id: number, start: number, duration: number, active = true): ShiftTemplate => ({
  id,
  name: `T${id}`,
  start_hour: start,
  duration_hours: duration,
  color: null,
  is_active: active,
});

describe("windowOf", () => {
  it("reads a daytime range", () => {
    expect(windowOf({ from: "06:00", to: "14:00" })).toEqual({ start_hour: 6, duration_hours: 8 });
  });

  it("reads minutes", () => {
    expect(windowOf({ from: "08:30", to: "16:00" })).toEqual({ start_hour: 8.5, duration_hours: 7.5 });
  });

  it("treats an earlier end as the next day", () => {
    const night = windowOf({ from: "22:00", to: "06:00" })!;
    expect(night).toEqual({ start_hour: 22, duration_hours: 8 });
    expect(crossesMidnight(night)).toBe(true);
  });

  it("refuses nonsense and empty ranges", () => {
    expect(windowOf({ from: "", to: "06:00" })).toBeNull();
    expect(windowOf({ from: "25:00", to: "06:00" })).toBeNull();
    expect(windowOf({ from: "06:00", to: "06:00" })).toBeNull();
  });
});

describe("labels", () => {
  it("shows a window as clock times, wrapping past midnight", () => {
    expect(windowLabel({ start_hour: 22, duration_hours: 8 })).toBe("22:00–06:00");
    expect(clock(24)).toBe("00:00");
    expect(rangeOf({ start_hour: 8.5, duration_hours: 7.5 })).toEqual({ from: "08:30", to: "16:00" });
  });
});

describe("matchingTemplate", () => {
  const all = [template(1, 6, 8), template(2, 14, 8, false), template(3, 22, 8)];

  it("finds a window with the same hours", () => {
    expect(matchingTemplate(all, { start_hour: 22, duration_hours: 8 })?.id).toBe(3);
  });

  it("skips removed windows and different hours", () => {
    expect(matchingTemplate(all, { start_hour: 14, duration_hours: 8 })).toBeUndefined();
    expect(matchingTemplate(all, { start_hour: 6, duration_hours: 7 })).toBeUndefined();
  });
});

describe("windowsOf", () => {
  it("drops duplicates and reports unreadable rows", () => {
    const result = windowsOf([
      { from: "06:00", to: "14:00" },
      { from: "06:00", to: "14:00" },
      { from: "", to: "" },
    ]);
    expect(result.windows).toHaveLength(1);
    expect(result.invalid).toBe(true);
  });
});
