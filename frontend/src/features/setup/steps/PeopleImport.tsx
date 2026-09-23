import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useDivisions, useLevels, useSkills } from "@/api/queries";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import {
  guessColumns,
  looksLikeHeader,
  parseTable,
  type ColumnChoice,
} from "@/lib/importing";
import type { ImportProblem, ImportRow, PeopleImport as ImportResult } from "@/types/api";
import { MutationError, WeekdayPicker, useDefaultWeek } from "./parts";

/**
 * Bringing a roster in from a spreadsheet.
 *
 * Three steps, each visible before the next: the table as read, what each
 * column means (guessed from its title, always changeable), and a row-by-row
 * preview from the server. Nothing is saved until the last button.
 */
export function PeopleImport({ onClose }: { onClose: () => void }) {
  const { t, tn } = useI18n();
  const { data: divisions } = useDivisions();
  const { data: skills } = useSkills();
  const { data: levels } = useLevels();
  const defaultWeek = useDefaultWeek();

  const [table, setTable] = useState<string[][] | null>(null);
  const [pasted, setPasted] = useState("");
  const [hasHeader, setHasHeader] = useState(true);
  const [columns, setColumns] = useState<ColumnChoice[]>([]);
  const [defaultDivision, setDefaultDivision] = useState<number | null>(null);
  const [defaultDays, setDefaultDays] = useState<number[]>(defaultWeek);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Reading a file saves nothing, so it invalidates nothing.
  const upload = useMutation({
    mutationFn: (file: File) =>
      api.upload<{ rows: string[][] }>("/api/config/import/table", file),
  });
  const run = useConfigMutation(
    (apply: boolean) =>
      api.post<ImportResult>("/api/config/import/people", {
        columns,
        rows: body,
        default_division_id: resolvedDivision,
        default_weekdays: defaultDays,
        apply,
      }),
    [keys.people, keys.divisions, keys.skills],
  );

  const width = table ? Math.max(...table.map((row) => row.length)) : 0;
  const header = table && hasHeader ? table[0]! : [];
  const body = useMemo(() => (table ? (hasHeader ? table.slice(1) : table) : []), [table, hasHeader]);

  function load(rows: string[][]) {
    if (!rows.length) return;
    const withHeader = looksLikeHeader(rows[0]!);
    setTable(rows);
    setHasHeader(withHeader);
    setColumns(guess(rows, withHeader));
    setPreview(null);
    setDone(null);
  }

  function guess(rows: string[][], withHeader: boolean): ColumnChoice[] {
    const columnCount = Math.max(...rows.map((row) => row.length));
    if (!withHeader) {
      // Without titles the first column is the likeliest place for names.
      return Array.from({ length: columnCount }, (_, i) => ({
        role: i === 0 ? "name" : "ignore",
      }));
    }
    const titles = Array.from({ length: columnCount }, (_, i) => rows[0]![i] ?? "");
    const guessed = guessColumns(
      titles,
      rows.slice(1),
      (skills ?? []).map((s) => s.name),
      (levels ?? []).map((l) => l.name),
    );
    if (!guessed.some((c) => c.role === "name")) guessed[0] = { role: "name" };
    return guessed;
  }

  async function onFile(file: File) {
    setUploadError(null);
    try {
      const result = await upload.mutateAsync(file);
      if (!result.rows.length) setUploadError(t("import.emptyFile"));
      load(result.rows);
    } catch (error) {
      setUploadError(errorText(error, t));
    }
  }

  function setColumn(index: number, value: string) {
    setPreview(null);
    setColumns((current) => {
      const next = [...current];
      if (value.startsWith("skill:")) next[index] = { role: "skill", skill_name: value.slice(6) };
      else next[index] = { role: value as ColumnChoice["role"] };
      // Only one column can hold names, divisions or days.
      if (["name", "division", "days"].includes(value)) {
        next.forEach((column, i) => {
          if (i !== index && column.role === value) next[i] = { role: "ignore" };
        });
      }
      return next;
    });
  }

  const hasName = columns.some((c) => c.role === "name");
  const hasDivisionColumn = columns.some((c) => c.role === "division");
  const resolvedDivision = defaultDivision ?? (hasDivisionColumn ? null : divisions?.[0]?.id ?? null);

  if (done !== null) {
    return (
      <div className="space-y-3 rounded-md border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-900 dark:bg-emerald-950/40">
        <p className="flex items-center gap-2 text-sm font-medium text-emerald-800 dark:text-emerald-300">
          <CheckCircle2 className="h-4 w-4" aria-hidden />
          {tn("import.imported", done)}
        </p>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => { setTable(null); setPasted(""); setDone(null); }}>
            {t("import.another")}
          </button>
          <button className="btn-primary" onClick={onClose}>{t("common.close")}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="h-4 w-4" aria-hidden />
        <h3 className="text-sm font-medium">{t("import.title")}</h3>
        <button className="btn-ghost ms-auto text-xs" onClick={onClose}>{t("common.close")}</button>
      </div>

      {!table && (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">{t("import.intro")}</p>
          <label className="btn-ghost cursor-pointer">
            <Upload className="h-4 w-4" aria-hidden />
            {upload.isPending ? t("common.working") : t("import.chooseFile")}
            <input
              type="file"
              className="sr-only"
              accept=".xlsx,.xlsm,.csv,.tsv,.txt"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void onFile(file);
              }}
            />
          </label>
          {uploadError && <ErrorNotice message={uploadError} />}

          <div>
            <label className="label" htmlFor="import-paste">{t("import.pasteLabel")}</label>
            <textarea
              id="import-paste"
              className="input min-h-32 font-mono text-xs"
              placeholder={t("import.pastePlaceholder")}
              value={pasted}
              onChange={(event) => setPasted(event.target.value)}
            />
          </div>
          <button
            className="btn-primary"
            disabled={!pasted.trim()}
            onClick={() => load(parseTable(pasted))}
          >
            {t("import.readTable")}
          </button>
        </div>
      )}

      {table && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="text-slate-500">{tn("import.rowsRead", body.length)}</span>
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={hasHeader}
                onChange={(event) => {
                  setHasHeader(event.target.checked);
                  setColumns(guess(table, event.target.checked));
                  setPreview(null);
                }}
              />
              {t("import.firstRowIsHeader")}
            </label>
            <button className="btn-ghost ms-auto text-xs" onClick={() => setTable(null)}>
              {t("import.startOver")}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  {Array.from({ length: width }, (_, index) => {
                    const title = header[index]?.trim() ?? "";
                    const choice = columns[index] ?? { role: "ignore" };
                    const value = choice.role === "skill" ? `skill:${choice.skill_name}` : choice.role;
                    const existingSkill = skills?.some(
                      (s) => s.name.toLowerCase() === title.toLowerCase(),
                    );
                    return (
                      <th key={index} className="th min-w-40 align-top normal-case">
                        <div className="mb-1 truncate font-medium text-slate-700 dark:text-slate-300">
                          {title || t("import.columnN", { n: index + 1 })}
                        </div>
                        <select
                          className="input py-1 text-xs"
                          value={value}
                          onChange={(event) => setColumn(index, event.target.value)}
                          aria-label={t("import.columnMeaning", { column: title || index + 1 })}
                        >
                          <option value="ignore">{t("import.role.ignore")}</option>
                          <option value="name">{t("import.role.name")}</option>
                          <option value="division">{t("import.role.division")}</option>
                          <option value="days">{t("import.role.days")}</option>
                          <optgroup label={t("import.role.skillGroup")}>
                            {skills?.map((skill) => (
                              <option key={skill.id} value={`skill:${skill.name}`}>{skill.name}</option>
                            ))}
                            {title && !existingSkill && (
                              <option value={`skill:${title}`}>
                                {t("import.role.newSkill", { name: title })}
                              </option>
                            )}
                            {choice.role === "skill" &&
                              choice.skill_name !== title &&
                              !skills?.some((s) => s.name === choice.skill_name) && (
                                <option value={value}>{choice.skill_name}</option>
                              )}
                          </optgroup>
                        </select>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {body.slice(0, 5).map((row, r) => (
                  <tr key={r} className="border-b border-slate-100 dark:border-slate-800/60">
                    {Array.from({ length: width }, (_, c) => (
                      <td
                        key={c}
                        className={`td max-w-48 truncate text-xs ${
                          columns[c]?.role === "ignore" ? "text-slate-400" : ""
                        }`}
                      >
                        {row[c] ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {body.length > 5 && (
              <p className="mt-1 text-xs text-slate-400">{tn("import.moreRows", body.length - 5)}</p>
            )}
          </div>

          {!hasName && <ErrorNotice message={t("import.needName")} />}

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="import-division">
                {hasDivisionColumn ? t("import.defaultDivisionBlank") : t("import.divisionForAll")}
              </label>
              <select
                id="import-division"
                className="input"
                value={resolvedDivision ?? ""}
                onChange={(event) => {
                  setDefaultDivision(event.target.value ? Number(event.target.value) : null);
                  setPreview(null);
                }}
              >
                <option value="">{t("import.noDefaultDivision")}</option>
                {divisions?.map((division) => (
                  <option key={division.id} value={division.id}>{division.name}</option>
                ))}
              </select>
            </div>
            <WeekdayPicker
              legend={
                columns.some((c) => c.role === "days")
                  ? t("import.defaultDaysBlank")
                  : t("import.daysForAll")
              }
              value={defaultDays}
              onChange={(days) => {
                setDefaultDays(days);
                setPreview(null);
              }}
            />
          </div>

          {!preview ? (
            <button
              className="btn-primary"
              disabled={!hasName || run.isPending}
              onClick={() => run.mutate(false, { onSuccess: setPreview })}
            >
              {run.isPending ? t("common.working") : t("import.check")}
            </button>
          ) : (
            <Preview
              result={preview}
              busy={run.isPending}
              onImport={() =>
                run.mutate(true, {
                  onSuccess: (result) => setDone(result.rows.filter((r) => r.status === "create").length),
                })
              }
            />
          )}

          <MutationError error={run.error} />
        </>
      )}
    </div>
  );
}

function Preview({
  result,
  busy,
  onImport,
}: {
  result: ImportResult;
  busy: boolean;
  onImport: () => void;
}) {
  const { t, tn } = useI18n();
  const [filter, setFilter] = useState<"all" | ImportRow["status"]>("all");
  const counts = {
    create: result.rows.filter((r) => r.status === "create").length,
    exists: result.rows.filter((r) => r.status === "exists").length,
    error: result.rows.filter((r) => r.status === "error").length,
  };
  const shown = result.rows.filter((row) => filter === "all" || row.status === filter);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-xs">
        {(["all", "create", "exists", "error"] as const).map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`badge ${filter === status ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : STATUS_TONES[status]}`}
          >
            {status === "all"
              ? t("import.filter.all", { count: result.rows.length })
              : tn(`import.status.${status}`, counts[status])}
          </button>
        ))}
      </div>

      {(result.new_divisions.length > 0 || result.new_skills.length > 0) && (
        <p className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          {result.new_divisions.length > 0 &&
            t("import.newDivisions", { names: result.new_divisions.join(", ") })}{" "}
          {result.new_skills.length > 0 &&
            t("import.newSkills", { names: result.new_skills.join(", ") })}
        </p>
      )}

      <div className="max-h-80 overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th className="th">{t("import.col.line")}</th>
              <th className="th">{t("common.name")}</th>
              <th className="th">{t("import.role.division")}</th>
              <th className="th">{t("import.col.result")}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.line} className="border-b border-slate-100 align-top dark:border-slate-800/60">
                <td className="td tabular-nums text-xs text-slate-400">{row.line}</td>
                <td className="td">{row.full_name || "—"}</td>
                <td className="td text-xs">{row.division ?? "—"}</td>
                <td className="td text-xs">
                  <span className={`badge ${STATUS_TONES[row.status]}`}>
                    {t(`import.rowStatus.${row.status}`)}
                  </span>
                  {row.problems.map((problem, index) => (
                    <div key={index} className="mt-1 text-rose-700 dark:text-rose-400">
                      <ProblemText problem={problem} />
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button className="btn-primary" disabled={busy || counts.create === 0} onClick={onImport}>
        {busy ? t("common.working") : tn("import.importCount", counts.create)}
      </button>
      {counts.error > 0 && <p className="text-xs text-slate-500">{t("import.errorsSkipped")}</p>}
    </div>
  );
}

const STATUS_TONES: Record<"all" | ImportRow["status"], string> = {
  all: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  create: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  exists: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  error: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
};

function ProblemText({ problem }: { problem: ImportProblem }) {
  const { t } = useI18n();
  return <>{t(`import.problem.${problem.code}`, { value: problem.value ?? "" })}</>;
}
