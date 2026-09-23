import { describe, expect, it } from "vitest";
import { guessColumns, looksLikeHeader, namesFrom, parseTable, parseWindowLine } from "./importing";

describe("parseWindowLine", () => {
  it("reads a start and end", () => {
    expect(parseWindowLine("Morning 06:00-14:00")).toEqual({
      name: "Morning",
      start_hour: 6,
      duration_hours: 8,
    });
  });

  it("reads a window that crosses midnight", () => {
    expect(parseWindowLine("לילה 22:00–06:00")).toEqual({
      name: "לילה",
      start_hour: 22,
      duration_hours: 8,
    });
  });

  it("reads a start and a length in hours", () => {
    expect(parseWindowLine("Night, 22:00, 8")).toEqual({
      name: "Night",
      start_hour: 22,
      duration_hours: 8,
    });
    expect(parseWindowLine("Evening\t14:30\t7.5")).toEqual({
      name: "Evening",
      start_hour: 14.5,
      duration_hours: 7.5,
    });
  });

  it("reads bare hours with a dash as an end time", () => {
    expect(parseWindowLine("בוקר 6-14")).toEqual({ name: "בוקר", start_hour: 6, duration_hours: 8 });
  });

  it("lets the name contain a number", () => {
    expect(parseWindowLine("Shift 2 14:00-22:00")?.name).toBe("Shift 2");
  });

  it("refuses what it cannot read rather than guessing", () => {
    expect(parseWindowLine("Morning")).toBeNull();
    expect(parseWindowLine("06:00-14:00")).toBeNull();
    expect(parseWindowLine("Morning 25:00-26:00")).toBeNull();
    expect(parseWindowLine("Long 06:00, 30")).toBeNull();
  });
});

describe("parseTable", () => {
  it("splits pasted spreadsheet cells on tabs, keeping commas inside names", () => {
    expect(parseTable("Name\tDivision\nCohen, Dana\tNorth\n")).toEqual([
      ["Name", "Division"],
      ["Cohen, Dana", "North"],
    ]);
  });

  it("handles quoted CSV", () => {
    expect(parseTable('name,division\r\n"Levi, ""Avi""",South')).toEqual([
      ["name", "division"],
      ['Levi, "Avi"', "South"],
    ]);
  });

  it("drops blank lines", () => {
    expect(parseTable("Dana\n\nAvi\n")).toEqual([["Dana"], ["Avi"]]);
  });
});

describe("namesFrom", () => {
  it("takes one name per line", () => {
    expect(namesFrom("North\n South \n\nEast")).toEqual(["North", "South", "East"]);
  });

  it("splits a single line on commas or tabs", () => {
    expect(namesFrom("North, South,East")).toEqual(["North", "South", "East"]);
    expect(namesFrom("צפון\tדרום")).toEqual(["צפון", "דרום"]);
  });

  it("uses only the first cell of each pasted row", () => {
    expect(namesFrom("North\t12\nSouth\t9")).toEqual(["North", "South"]);
  });
});

describe("guessColumns", () => {
  const body = [
    ["Dana", "צפון", "א-ה", "Expert", "x", "050-1234567"],
    ["Avi", "דרום", "ב-ו", "", "", "052-7654321"],
  ];

  it("recognises English and Hebrew headers, skills, and level-like columns", () => {
    expect(
      guessColumns(
        ["שם", "מחלקה", "ימי עבודה", "driving", "Medic", "Phone"],
        body,
        ["Driving"],
        ["Basic", "Expert"],
      ),
    ).toEqual([
      { role: "name" },
      { role: "division" },
      { role: "days" },
      { role: "skill", skill_name: "Driving" },
      { role: "skill", skill_name: "Medic" },
      { role: "ignore" },
    ]);
  });

  it("detects a header row", () => {
    expect(looksLikeHeader(["Name", "Team"])).toBe(true);
    expect(looksLikeHeader(["Dana Cohen", "North"])).toBe(false);
  });
});
