import { describe, expect, it } from "vitest";
import type { BoardShift } from "./dayBoard";
import { dayText, daysText, whatsappLink, type ShareLabels } from "./share";

const labels: ShareLabels = {
  heading: (d) => `Roster ${d}`,
  away: "Away",
  missing: (n) => `${n} missing`,
  noShifts: "No shifts",
};

const board: BoardShift[] = [
  {
    templateId: 1,
    window: "Morning",
    start: "06:00",
    end: "14:00",
    startHour: 6,
    jobs: [
      {
        jobId: 1,
        job: "Patrol",
        required: 3,
        present: 1,
        missing: 2,
        people: [
          { id: 1, name: "Avi", away: null },
          { id: 2, name: "Dana", away: "Leave" },
        ],
      },
      { jobId: 2, job: "Driver", required: null, present: 1, missing: 0, people: [{ id: 3, name: "Lee", away: null }] },
    ],
  },
];

describe("dayText", () => {
  it("writes a heading, each shift and each task with who works it", () => {
    const text = dayText({ dateLabel: "Sun", board, absences: [] }, labels);
    expect(text).toBe(
      ["*Roster Sun*", "", "*Morning 06:00–14:00*", "• Patrol (1/3): Avi, ~Dana~ ⚠️ 2 missing", "• Driver (1): Lee"].join(
        "\n",
      ),
    );
  });

  it("lists who is away, with the reason when there is one", () => {
    const text = dayText(
      { dateLabel: "Sun", board: [], absences: [{ name: "Dana", note: "Leave" }, { name: "Avi", note: "" }] },
      labels,
    );
    expect(text).toContain("No shifts");
    expect(text).toContain("*Away*\n• Dana — Leave\n• Avi");
  });
});

describe("daysText", () => {
  it("separates days", () => {
    const text = daysText(
      [
        { dateLabel: "Sun", board: [], absences: [] },
        { dateLabel: "Mon", board: [], absences: [] },
      ],
      labels,
    );
    expect(text).toContain("*Roster Sun*");
    expect(text).toContain("*Roster Mon*");
    expect(text).toContain("――――");
  });
});

describe("whatsappLink", () => {
  it("encodes the text", () => {
    expect(whatsappLink("a b\n*c*")).toBe("https://wa.me/?text=a%20b%0A*c*");
  });

  it("gives up on text too long for a link", () => {
    expect(whatsappLink("x".repeat(8000))).toBeNull();
  });
});
