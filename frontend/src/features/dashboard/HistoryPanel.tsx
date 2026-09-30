import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { History, Undo2 } from "lucide-react";
import { useToast } from "@/components/Toasts";
import { historyKey, runKeys, undoEdit, useHistory } from "@/api/queries";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { HistoryEntry, ScheduleRun } from "@/types/api";

/** Who changed what after the schedule was generated, with undo for the newest change. */
export function HistoryPanel({ run }: { run: ScheduleRun }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  // Fetched only once opened, but refreshed whenever the schedule changes.
  const history = useHistory(run.schedule_id, open);

  const undo = useMutation({
    mutationFn: (entry: HistoryEntry) => undoEdit(run.schedule_id, entry.id),
    onSuccess: (updated) => {
      toast(t("toast.undone"));
      queryClient.setQueryData(runKeys.latest, updated);
      void queryClient.invalidateQueries({ queryKey: historyKey(run.schedule_id) });
    },
  });

  const describe = (entry: HistoryEntry): string => {
    const params = {
      job: entry.job_name ?? "",
      date: entry.calendar_date ? formatDate(entry.calendar_date) : "",
      from: entry.person_before ?? "",
      to: entry.person_after ?? "",
      who: entry.user_name ?? t("history.someone"),
    };
    switch (entry.action) {
      case "reassign":
        return t("history.reassign", params);
      case "add":
        return t("history.add", params);
      case "remove":
        return t("history.remove", params);
      case "lock":
        return t("history.lock", params);
      default:
        return t("history.unlock", params);
    }
  };

  return (
    <section className="card space-y-3 print:hidden">
      <button
        className="flex items-center gap-2 text-sm font-medium"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <History className="h-4 w-4 text-slate-400" aria-hidden />
        {t("history.title")}
      </button>

      {open && (
        <>
          {undo.error ? <ErrorNotice message={errorText(undo.error, t)} /> : null}
          {!history.data?.length ? (
            <p className="text-sm text-slate-500">{t("history.empty")}</p>
          ) : (
            <ul className="max-h-64 space-y-1 overflow-auto">
              {history.data.map((entry) => (
                <li
                  key={entry.id}
                  className={`flex items-center gap-2 text-sm ${entry.undone ? "text-slate-400 line-through" : ""}`}
                >
                  <span className="flex-1">{describe(entry)}</span>
                  {entry.at && (
                    <time className="shrink-0 text-xs text-slate-400" dateTime={entry.at}>
                      {new Date(entry.at).toLocaleString()}
                    </time>
                  )}
                  {entry.can_undo && (
                    <button
                      className="btn-ghost px-2 py-0.5 text-xs"
                      disabled={undo.isPending}
                      onClick={() => undo.mutate(entry)}
                    >
                      <Undo2 className="h-3.5 w-3.5" aria-hidden />
                      {t("history.undo")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
