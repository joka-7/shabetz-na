import { describe, expect, it } from "vitest";
import { pathForTab, tabFromPath } from "./tabRoute";

describe("tab routes", () => {
  it("round-trip every tab through its path", () => {
    for (const tab of ["dashboard", "timeoff", "swaps", "attendance", "tasks", "config"] as const) {
      expect(tabFromPath(pathForTab(tab))).toBe(tab);
    }
  });

  it("ignore a trailing slash and open the schedule for anything unknown", () => {
    expect(tabFromPath("/swaps/")).toBe("swaps");
    expect(tabFromPath("/no-such-page")).toBe("dashboard");
    expect(tabFromPath("")).toBe("dashboard");
  });
});
