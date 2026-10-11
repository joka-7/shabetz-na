import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, FileUp } from "lucide-react";
import { api, downloadBackup } from "@/api/client";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { MessageKey } from "@/i18n";
import type { BackupImportResult } from "@/types/api";

const ENTITIES = [
  "settings",
  "divisions",
  "levels",
  "skills",
  "shift_templates",
  "jobs",
  "people",
  "time_off",
] as const;

/**
 * Saving the project to a file and bringing a file back.
 *
 * Importing merges by name: what the file names is added if missing and brought
 * in line if it exists; nothing in the project is removed. The same file can
 * therefore be loaded into a new project, or into this one to update it. A
 * preview shows what would change before anything is saved.
 */
export function BackupPanel() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [backup, setBackup] = useState<unknown>(null);
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<BackupImportResult | null>(null);
  const [done, setDone] = useState<BackupImportResult | null>(null);
  const [readError, setReadError] = useState<string | null>(null);

  // The file's contents travel with each request: state set a moment ago has
  // not reached this closure yet, which is when the preview is asked for.
  const run = useMutation({
    mutationFn: ({ contents, apply }: { contents: unknown; apply: boolean }) =>
      api.post<BackupImportResult>("/api/config/backup/import", { backup: contents, apply }),
  });

  async function onFile(file: File) {
    setReadError(null);
    setPreview(null);
    setDone(null);
    run.reset();
    try {
      const parsed: unknown = JSON.parse(await file.text());
      setBackup(parsed);
      setFileName(file.name);
      run.mutate({ contents: parsed, apply: false }, { onSuccess: setPreview });
    } catch {
      setBackup(null);
      setReadError(t("error.badBackup"));
    }
  }

  function apply() {
    run.mutate({ contents: backup, apply: true }, {
      onSuccess: (result) => {
        setDone(result);
        setPreview(null);
        // Almost everything on screen may have changed.
        void queryClient.invalidateQueries();
      },
    });
  }

  const shown = done ?? preview;
  const changes = shown
    ? Object.values(shown.counts).reduce((sum, c) => sum + c.created + c.updated, 0)
    : 0;

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-medium">{t("backup.title")}</h2>
        <p className="mt-1 text-sm text-slate-500">{t("backup.intro")}</p>
      </div>

      <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
        <h3 className="text-sm font-medium">{t("backup.saveHeading")}</h3>
        <p className="mb-2 text-xs text-slate-500">{t("backup.saveHint")}</p>
        <button className="btn-primary" onClick={downloadBackup}>
          <Download className="h-4 w-4" aria-hidden />
          {t("backup.download")}
        </button>
      </div>

      <div className="space-y-3 rounded-md border border-slate-200 p-3 dark:border-slate-700">
        <h3 className="text-sm font-medium">{t("backup.restoreHeading")}</h3>
        <p className="text-xs text-slate-500">{t("backup.restoreHint")}</p>
        <label className="btn-ghost cursor-pointer">
          <FileUp className="h-4 w-4" aria-hidden />
          {run.isPending && !shown ? t("common.working") : t("backup.chooseFile")}
          <input
            type="file"
            className="sr-only"
            accept=".json,application/json"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void onFile(file);
            }}
          />
        </label>
        {fileName && <span className="ms-2 text-xs text-slate-500">{fileName}</span>}
        {readError && <ErrorNotice message={readError} />}
        {run.error ? <ErrorNotice message={errorText(run.error, t)} /> : null}

        {shown && (
          <div className="space-y-3">
            {done ? (
              <p className="flex items-center gap-2 text-sm font-medium text-emerald-800 dark:text-emerald-300">
                <CheckCircle2 className="h-4 w-4" aria-hidden />
                {t("backup.done")}
              </p>
            ) : (
              <p className="text-sm font-medium">{t("backup.previewHeading")}</p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    <th className="th">{t("backup.col.what")}</th>
                    <th className="th">{t("backup.col.created")}</th>
                    <th className="th">{t("backup.col.updated")}</th>
                    <th className="th">{t("backup.col.unchanged")}</th>
                  </tr>
                </thead>
                <tbody>
                  {ENTITIES.filter((entity) => shown.counts[entity]).map((entity) => {
                    const c = shown.counts[entity]!;
                    return (
                      <tr key={entity} className="border-b border-slate-100 dark:border-slate-700/60">
                        <td className="td">{t(`backup.entity.${entity}` as MessageKey)}</td>
                        <td className="td tabular-nums">{c.created}</td>
                        <td className="td tabular-nums">{c.updated}</td>
                        <td className="td tabular-nums text-slate-400">{c.unchanged}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {shown.problems.length > 0 && (
              <ul className="space-y-1 text-xs text-red-700 dark:text-red-400">
                {shown.problems.map((problem, index) => (
                  <li key={index}>
                    {t(`backup.problem.${problem.code}` as MessageKey, { value: problem.value })}
                  </li>
                ))}
              </ul>
            )}
            {!done && (
              <button className="btn-primary" disabled={run.isPending || changes === 0} onClick={apply}>
                {changes === 0 ? t("backup.nothingToDo") : t("backup.apply")}
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
