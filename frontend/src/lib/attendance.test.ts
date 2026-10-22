import { describe, expect, it } from "vitest";
import type { AttendanceRow } from "@/types/api";
import { absencesOf, awayMap, reportText, standing, summarize, type ReportLabels } from "./attendance";
import type { BoardShift } from "./dayBoard";

const row = (over: Partial<AttendanceRow>): AttendanceRow => ({
  person_id: 1,
  full_name: "Avi",
  division_id: 1,
  status: null,
  note: null,
  on_leave: false,
  leave_reason: null,
  ...over,
});

const labels = { absent: "Absent", leave: "On leave" };

describe("standing", () => {
  it("is what was marked, else leave, else unmarked", () => {
    expect(standing(row({ status: "PRESENT" }))).toBe("present");
    expect(standing(row({ status: "ABSENT" }))).toBe("absent");
    expect(standing(row({ on_leave: true }))).toBe("leave");
    expect(standing(row({}))).toBe("unmarked");
  });

  it("lets an explicit present win over approved leave", () => {
    expect(standing(row({ status: "PRESENT", on_leave: true }))).toBe("present");
  });
});

describe("awayMap and absencesOf", () => {
  const rows = [
    row({ person_id: 1, full_name: "Avi", status: "ABSENT", note: "Sick" }),
    row({ person_id: 2, full_name: "Dana", on_leave: true, leave_reason: "Trip" }),
    row({ person_id: 3, full_name: "Lee", on_leave: true }),
    row({ person_id: 4, full_name: "Noa", status: "PRESENT", on_leave: true }),
    row({ person_id: 5, full_name: "Gil" }),
  ];

  it("maps the people who cannot be counted on, with a reason", () => {
    expect([...awayMap(rows, labels)]).toEqual([
      [1, "Sick"],
      [2, "Trip"],
      [3, "On leave"],
    ]);
  });

  it("lists them for a message", () => {
    expect(absencesOf(rows, labels)).toEqual([
      { name: "Avi", note: "Sick" },
      { name: "Dana", note: "Trip" },
      { name: "Lee", note: "On leave" },
    ]);
  });
});

describe("summarize", () => {
  it("counts each standing", () => {
    expect(
      summarize([
        row({ status: "PRESENT" }),
        row({ status: "PRESENT" }),
        row({ status: "ABSENT" }),
        row({ on_leave: true }),
        row({}),
      ]),
    ).toEqual({ total: 5, present: 2, absent: 1, leave: 1, unmarked: 1 });
  });
});

describe("reportText", () => {
  const report: ReportLabels = {
    heading: (d) => `Status ${d}`,
    totals: (s) => `${s.total} people: ${s.present} present, ${s.absent} absent`,
    absent: "Absent",
    leave: "On leave",
    unmarked: "Not marked",
    gap: (shift, job, n) => `${shift} · ${job}: ${n} missing`,
    gaps: "Short",
    allCovered: "All shifts covered",
  };
  const board: BoardShift[] = [
    {
      templateId: 1,
      window: "Morning",
      start: "06:00",
      end: "14:00",
      startHour: 6,
      jobs: [{ jobId: 1, job: "Patrol", required: 3, present: 1, missing: 2, people: [] }],
    },
  ];

  it("gives counts, who is away, who is unmarked and what is short", () => {
    const text = reportText(
      "Sun",
      [
        row({ full_name: "Avi", status: "ABSENT", note: "Sick" }),
        row({ full_name: "Dana", status: "PRESENT" }),
        row({ full_name: "Gil" }),
      ],
      board,
      report,
    );
    expect(text).toBe(
      [
        "*Status Sun*",
        "3 people: 1 present, 1 absent",
        "",
        "*Absent*",
        "• Avi — Sick",
        "",
        "*Not marked*",
        "• Gil",
        "",
        "*Short*",
        "• Morning 06:00–14:00 · Patrol: 2 missing",
      ].join("\n"),
    );
  });

  it("says so when every shift is covered", () => {
    const covered: BoardShift[] = [
      { ...board[0]!, jobs: [{ ...board[0]!.jobs[0]!, present: 3, missing: 0 }] },
    ];
    expect(reportText("Sun", [row({ status: "PRESENT" })], covered, report)).toContain(
      "All shifts covered",
    );
  });

  it("stays quiet about shifts when none are scheduled", () => {
    const text = reportText("Sun", [row({ status: "PRESENT" })], [], report);
    expect(text).not.toContain("All shifts covered");
  });
});
