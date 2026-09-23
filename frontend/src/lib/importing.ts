/**
 * Reading pasted text: shift windows written as a line each, and tables copied
 * out of a spreadsheet. Pure functions, so they are tested directly.
 */

/** Non-empty trimmed lines. */
export function splitLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

/**
 * Names from pasted text, however they were laid out.
 *
 * One per line is the usual shape (a spreadsheet column). A single line is
 * split on tabs or commas instead, which covers a copied spreadsheet row and a
 * typed "North, South, East". With several lines, only the first cell of each
 * is used, so pasting a whole table does not turn every cell into a name.
 */
export function namesFrom(text: string): string[] {
  const lines = splitLines(text);
  const cells =
    lines.length === 1
      ? lines[0]!.split(/[\t,]/)
      : lines.map((line) => line.split("\t")[0]!);
  return cells.map((cell) => cell.trim()).filter(Boolean);
}

export interface WindowDraft {
  name: string;
  start_hour: number;
  duration_hours: number;
}

const TIME = /(\d{1,2})(?:[:.](\d{2}))?/;

function hours(match: RegExpMatchArray): number | null {
  const h = Number(match[1]);
  const m = match[2] === undefined ? 0 : Number(match[2]);
  if (h > 24 || m >= 60) return null;
  return h + m / 60;
}

/**
 * One shift window from a line such as
 *
 *   Morning 06:00-14:00      (a start and an end; may cross midnight)
 *   Night, 22:00, 8          (a start and a length in hours)
 *   בוקר 6-14
 *
 * The name is everything before the first time. After a dash, or when it has
 * minutes, the second number is an end time; a bare number is a length.
 */
export function parseWindowLine(line: string): WindowDraft | null {
  const cleaned = line.replace(/\t/g, " ").trim();
  // A name may itself hold a number ("Shift 2 06:00-14:00"), so each number
  // is tried as the start until one leaves a readable remainder.
  for (const match of cleaned.matchAll(new RegExp(TIME.source, "g"))) {
    const parsed = parseFrom(cleaned, match);
    if (parsed) return parsed;
  }
  return null;
}

function parseFrom(cleaned: string, first: RegExpMatchArray): WindowDraft | null {
  if (first.index === undefined) return null;
  const name = cleaned.slice(0, first.index).replace(/[\s,;:|-]+$/, "").trim();
  const start = hours(first);
  if (!name || start === null || start >= 24) return null;

  const rest = cleaned.slice(first.index + first[0].length);
  const second = rest.match(
    /^\s*([-–—]|,|;|\s)\s*(\d{1,2}(?:[:.]\d{2})?|\d+(?:\.\d+)?)\s*(?:h|hours|שעות)?\s*$/i,
  );
  if (!second) return null;

  const [, separator, value] = second;
  const isEnd = /[-–—]/.test(separator!) || value!.includes(":");
  let duration: number;
  if (isEnd) {
    const end = hours(value!.match(TIME)!);
    if (end === null) return null;
    duration = end - start;
    if (duration <= 0) duration += 24;
  } else {
    duration = Number(value);
  }
  if (!(duration > 0 && duration <= 24)) return null;
  return { name, start_hour: start, duration_hours: Math.round(duration * 100) / 100 };
}

/** Split pasted CSV or TSV into rows of cells, handling quoted cells. */
export function parseTable(text: string): string[][] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const sample = lines.slice(0, 20).join("\n");
  const delimiter = sample.includes("\t")
    ? "\t"
    : (sample.match(/;/g)?.length ?? 0) > (sample.match(/,/g)?.length ?? 0)
      ? ";"
      : ",";

  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const input = text.replace(/\r\n?/g, "\n");

  for (let i = 0; i < input.length; i++) {
    const char = input[i]!;
    if (quoted) {
      if (char === '"' && input[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
    } else if (char === '"' && cell === "") {
      quoted = true;
    } else if (char === delimiter) {
      row.push(cell.trim());
      cell = "";
    } else if (char === "\n") {
      row.push(cell.trim());
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  row.push(cell.trim());
  rows.push(row);

  return rows
    .map((cells) => {
      const trimmed = [...cells];
      while (trimmed.length && !trimmed[trimmed.length - 1]) trimmed.pop();
      return trimmed;
    })
    .filter((cells) => cells.length > 0);
}

export type ColumnRole = "name" | "division" | "days" | "skill" | "ignore";

export interface ColumnChoice {
  role: ColumnRole;
  skill_name?: string;
}

const HEADER_WORDS: Record<Exclude<ColumnRole, "skill" | "ignore">, string[]> = {
  name: ["name", "full name", "fullname", "person", "employee", "worker", "שם", "שם מלא", "עובד", "עובדת", "שם העובד"],
  division: ["division", "team", "group", "department", "unit", "מחלקה", "צוות", "קבוצה", "יחידה", "אגף"],
  days: ["days", "working days", "workdays", "work days", "ימים", "ימי עבודה", "ימי עבודה בשבוע"],
};

const normalise = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ");

/**
 * What a header most likely means.
 *
 * A header naming an existing skill is that skill. Any other unrecognised
 * header becomes a new skill only if its cells look like levels or ticks;
 * otherwise it is ignored, so a column like "Phone" is never turned into a
 * skill without the person choosing that.
 */
export function guessColumns(
  header: string[],
  body: string[][],
  skillNames: string[],
  levelNames: string[],
): ColumnChoice[] {
  const skills = new Map(skillNames.map((name) => [normalise(name), name]));
  const levels = new Set(levelNames.map(normalise));
  const ticks = new Set(["x", "v", "✓", "✔", "✅", "+", "yes", "כן"]);
  const used = new Set<ColumnRole>();

  return header.map((raw, index) => {
    const title = normalise(raw);
    for (const role of ["name", "division", "days"] as const) {
      if (!used.has(role) && HEADER_WORDS[role].includes(title)) {
        used.add(role);
        return { role };
      }
    }
    const skill = skills.get(title);
    if (skill) return { role: "skill", skill_name: skill };

    const values = body.map((cells) => normalise(cells[index] ?? "")).filter(Boolean);
    const looksLikeLevels =
      values.length > 0 && values.every((value) => levels.has(value) || ticks.has(value));
    if (raw.trim() && looksLikeLevels) return { role: "skill", skill_name: raw.trim() };
    return { role: "ignore" };
  });
}

/** Whether the first row reads as column titles rather than a person. */
export function looksLikeHeader(firstRow: string[]): boolean {
  return firstRow.some((cell) => {
    const title = normalise(cell);
    return Object.values(HEADER_WORDS).some((words) => words.includes(title));
  });
}
