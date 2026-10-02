import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, History, Lock, Pencil, Plus, Send, Trash2, Undo2, Unlock } from "lucide-react";
import { historyKey, runKeys, undoEdit, useHistory } from "@/api/queries";
import { ErrorNotice } from "@/components/ui";
import { useToast } from "@/components/Toasts";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { HistoryEntry, ScheduleRun } from "@/types/api";

const ICON = {
  reassign: Pencil,
  swap: ArrowLeftRight,
  add: Plus,
  remove: Trash2,
  lock: Lock,
  unlock: Unlock,
  publish: Send,
} as const;

/** Who changed what after the schedule was generated, with undo for the newest change. */
export function HistoryPanel({ run }: { run: ScheduleRun }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const history = useHistory(run.schedule_id, true);

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
      date: entry.calendar_date ?? "",
      from: entry.person_before ?? "",
      to: entry.person_after ?? "",
      who: entry.user_name ?? t("history.someone"),
    };
    switch (entry.action) {
      case "reassign":
        return t("history.reassign", params);
      case "swap":
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
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <History className="h-4 w-4 text-indigo-500" aria-hidden />
        {t("history.title")}
      </h2>
      {undo.error ? <ErrorNotice message={errorText(undo.error, t)} /> : null}
      {!history.data?.length ? (
        <p className="text-sm text-slate-500">{t("history.empty")}</p>
      ) : (
        <ul className="max-h-80 space-y-2 overflow-auto">
          {history.data.map((entry) => {
            const Icon = ICON[entry.action] ?? Pencil;
            return (
              <li
                key={entry.id}
                className={`rounded-lg border p-2.5 text-sm ${
                  entry.undone
                    ? "border-slate-200 text-slate-400 line-through dark:border-slate-700"
                    : "border-indigo-100 bg-indigo-50/60 dark:border-indigo-900 dark:bg-indigo-950/40"
                }`}
              >
                <div className="flex items-start gap-2">
                  <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-500" aria-hidden />
                  <span className="flex-1">{describe(entry)}</span>
                  {entry.can_undo && (
                    <button
                      className="btn-primary shrink-0 px-2 py-0.5 text-xs"
                      disabled={undo.isPending}
                      onClick={() => undo.mutate(entry)}
                    >
                      <Undo2 className="h-3 w-3" aria-hidden />
                      {t("history.undo")}
                    </button>
                  )}
                </div>
                {entry.at && (
                  <time className="mt-1 block text-[11px] text-slate-400" dateTime={entry.at}>
                    {new Date(entry.at).toLocaleString()}
                  </time>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
