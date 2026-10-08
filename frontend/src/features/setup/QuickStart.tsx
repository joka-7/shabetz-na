import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, CheckCircle2, Download, FileSpreadsheet, Upload } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useDivisions, useLevels, useSkills } from "@/api/queries";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import {
  analyzeRoster,
  looksLikeHeader,
  parseTable,
  rosterTemplate,
  summarizeRoster,
  type ColumnChoice,
} from "@/lib/importing";
import type { BulkResult, PeopleImport as ImportResult } from "@/types/api";
import { MutationError, useDefaultWeek } from "./steps/parts";

/**
 * Setting everything up from one roster file.
 *
 * The file's column titles say what each column is; divisions, skills and
 * levels are read off its cells. Nothing is saved until the button, and the
 * wizard's own steps stay available afterwards for anything to adjust.
 */
export function QuickStart({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t, tn, lang } = useI18n();
  const { data: skills } = useSkills();
  const { data: levels } = useLevels();
  const { data: divisions } = useDivisions();
  const defaultWeek = useDefaultWeek();

  const [table, setTable] = useState<string[][] | null>(null);
  const [hasHeader, setHasHeader] = useState(true);
  const [columns, setColumns] = useState<ColumnChoice[]>([]);
  const [levelOrder, setLevelOrder] = useState<string[]>([]);
  const [pasted, setPasted] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  const known = useMemo(
    () => ({ skills: (skills ?? []).map((s) => s.name), levels: (levels ?? []).map((l) => l.name) }),
    [skills, levels],
  );
  const body = useMemo(
    () => (table ? (hasHeader ? table.slice(1) : table) : []),
    [table, hasHeader],
  );
  const header = table && hasHeader ? table[0]! : [];
  const width = table ? Math.max(...table.map((row) => row.length)) : 0;
  const summary = useMemo(() => summarizeRoster(columns, body, known), [columns, body, known]);

  // Keep the user's ordering of levels while following any column changes.
  const orderedLevels = useMemo(
    () => [
      ...levelOrder.filter((l) => summary.levels.includes(l)),
      ...summary.levels.filter((l) => !levelOrder.includes(l)),
    ],
    [levelOrder, summary.levels],
  );

  const upload = useMutation({
    mutationFn: (file: File) => api.upload<{ rows: string[][] }>("/api/config/import/table", file),
  });

  const apply = useConfigMutation(
    async () => {
      // The ladder first, because people's skills refer to its levels.
      const needsLevels = summary.skills.length > 0 && !known.levels.length && !orderedLevels.length;
      const newLevels = needsLevels ? [t("ladder.yesName")] : orderedLevels;
      if (newLevels.length) {
        await api.post<BulkResult>("/api/config/proficiency-levels/bulk", { names: newLevels });
      }
      if (summary.skills.length) await api.post<BulkResult>("/api/config/skills/bulk", { names: summary.skills });
      if (summary.divisions.length) {
        await api.post<BulkResult>("/api/config/divisions/bulk", { names: summary.divisions });
      }
      return api.post<ImportResult>("/api/config/import/people", {
        columns,
        rows: body,
        default_division_id: summary.divisions.length ? null : divisions?.[0]?.id ?? null,
        default_weekdays: defaultWeek,
        apply: true,
      });
    },
    [keys.people, keys.divisions, keys.skills, keys.levels],
  );

  function load(rows: string[][]) {
    if (!rows.length) {
      setFileError(t("import.emptyFile"));
      return;
    }
    const withHeader = looksLikeHeader(rows[0]!);
    const analysis = withHeader
      ? analyzeRoster(rows[0]!, rows.slice(1), known)
      : { columns: rows[0]!.map((_, i): ColumnChoice => ({ role: i === 0 ? "name" : "ignore" })) };
    setTable(rows);
    setHasHeader(withHeader);
    setColumns(analysis.columns);
    setLevelOrder([]);
  }

  async function onFile(file: File) {
    setFileError(null);
    try {
      load((await upload.mutateAsync(file)).rows);
    } catch (error) {
      setFileError(errorText(error, t));
    }
  }

  function setRole(index: number, value: string) {
    setColumns((current) => {
      const next = [...current];
      next[index] =
        value === "skill"
          ? { role: "skill", skill_name: header[index]?.trim() || t("import.columnN", { n: index + 1 }) }
          : { role: value as ColumnChoice["role"] };
      if (["name", "division", "days"].includes(value)) {
        next.forEach((c, i) => i !== index && c.role === value && (next[i] = { role: "ignore" }));
      }
      return next;
    });
  }

  function moveLevel(index: number, delta: number) {
    const next = [...orderedLevels];
    const [moved] = next.splice(index, 1);
    next.splice(index + delta, 0, moved!);
    setLevelOrder(next);
  }

  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob([rosterTemplate(lang)], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "shabetz-roster.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  if (result) {
    const created = result.rows.filter((r) => r.status === "create").length;
    const problems = result.rows.filter((r) => r.status === "error").length;
    return (
      <div className="card space-y-3 border-emerald-300 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40">
        <p className="flex items-center gap-2 text-sm font-medium text-emerald-800 dark:text-emerald-300">
          <CheckCircle2 className="h-4 w-4" aria-hidden />
          {tn("quick.done", created)}
        </p>
        {problems > 0 && <p className="text-xs text-slate-600 dark:text-slate-400">{tn("quick.skipped", problems)}</p>}
        <button className="btn-primary" onClick={onDone}>{t("quick.continue")}</button>
      </div>
    );
  }

  const hasName = columns.some((c) => c.role === "name");

  return (
    <div className="card space-y-4">
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="h-4 w-4" aria-hidden />
        <h2 className="text-base font-semibold">{t("quick.title")}</h2>
        <button className="btn-ghost ms-auto text-xs" onClick={onClose}>{t("common.close")}</button>
      </div>

      {!table ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">{t("quick.intro")}</p>
          <div
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              const file = event.dataTransfer.files?.[0];
              if (file) void onFile(file);
            }}
            className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center ${
              dragging ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950" : "border-slate-300 dark:border-slate-600"
            }`}
          >
            <Upload className="h-6 w-6 text-slate-400" aria-hidden />
            <label className="btn-primary cursor-pointer">
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
            <span className="text-xs text-slate-500">{t("quick.drop")}</span>
          </div>
          {fileError && <ErrorNotice message={fileError} />}
          <div>
            <label className="label" htmlFor="quick-paste">{t("import.pasteLabel")}</label>
            <textarea
              id="quick-paste"
              className="input min-h-28 font-mono text-xs"
              placeholder={t("import.pastePlaceholder")}
              value={pasted}
              onChange={(event) => setPasted(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" disabled={!pasted.trim()} onClick={() => load(parseTable(pasted))}>
              {t("import.readTable")}
            </button>
            <button className="btn-ghost" onClick={downloadTemplate}>
              <Download className="h-4 w-4" aria-hidden />
              {t("quick.template")}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="text-slate-500">{tn("import.rowsRead", body.length)}</span>
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={hasHeader}
                onChange={(event) => {
                  const withHeader = event.target.checked;
                  setHasHeader(withHeader);
                  setColumns(
                    withHeader
                      ? analyzeRoster(table[0]!, table.slice(1), known).columns
                      : table[0]!.map((_, i): ColumnChoice => ({ role: i === 0 ? "name" : "ignore" })),
                  );
                }}
              />
              {t("import.firstRowIsHeader")}
            </label>
            <button className="btn-ghost ms-auto text-xs" onClick={() => setTable(null)}>
              {t("import.startOver")}
            </button>
          </div>

          <div>
            <h3 className="mb-1 text-sm font-medium">{t("quick.columns")}</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: width }, (_, index) => {
                const title = header[index]?.trim() || t("import.columnN", { n: index + 1 });
                const role = columns[index]?.role ?? "ignore";
                return (
                  <label key={index} className="text-xs">
                    <span className="mb-0.5 block truncate font-medium">{title}</span>
                    <select
                      className="input py-1 text-xs"
                      value={role}
                      onChange={(event) => setRole(index, event.target.value)}
                      aria-label={t("import.columnMeaning", { column: title })}
                    >
                      <option value="ignore">{t("import.role.ignore")}</option>
                      <option value="name">{t("import.role.name")}</option>
                      <option value="division">{t("import.role.division")}</option>
                      <option value="days">{t("import.role.days")}</option>
                      <option value="skill">{t("quick.role.skill")}</option>
                    </select>
                  </label>
                );
              })}
            </div>
          </div>

          {!hasName && <ErrorNotice message={t("import.needName")} />}

          <ul className="space-y-1 rounded-md bg-slate-100 p-3 text-sm dark:bg-slate-800">
            <li>{t("quick.foundDivisions", { names: summary.divisions.join(", ") || "—" })}</li>
            <li>{t("quick.foundSkills", { names: summary.skills.join(", ") || "—" })}</li>
            <li>{tn("quick.foundPeople", body.filter((r) => r.some(Boolean)).length)}</li>
          </ul>

          {orderedLevels.length > 0 && (
            <div>
              <h3 className="text-sm font-medium">{t("quick.levelsHeading")}</h3>
              <p className="mb-1 text-xs text-slate-500">{t("quick.levelsHint")}</p>
              <ol className="divide-y divide-slate-100 dark:divide-slate-700">
                {orderedLevels.map((name, index) => (
                  <li key={name} className="flex items-center gap-2 py-1 text-sm">
                    <span className="w-5 text-xs tabular-nums text-slate-400">{index + 1}</span>
                    <span className="flex-1">{name}</span>
                    <button
                      className="btn-ghost px-1.5 py-1"
                      disabled={index === 0}
                      onClick={() => moveLevel(index, -1)}
                      aria-label={t("quick.levelWeaker", { name })}
                    >
                      <ArrowUp className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <button
                      className="btn-ghost px-1.5 py-1"
                      disabled={index === orderedLevels.length - 1}
                      onClick={() => moveLevel(index, 1)}
                      aria-label={t("quick.levelStronger", { name })}
                    >
                      <ArrowDown className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <p className="text-xs text-slate-500">{t("quick.skipNote")}</p>
          <button className="btn-primary" disabled={!hasName || apply.isPending} onClick={() => apply.mutate(undefined, { onSuccess: setResult })}>
            {apply.isPending ? t("common.working") : t("quick.apply")}
          </button>
          <MutationError error={apply.error} />
        </div>
      )}
    </div>
  );
}
