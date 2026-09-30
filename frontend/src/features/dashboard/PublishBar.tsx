import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Send } from "lucide-react";
import { useToast } from "@/components/Toasts";
import { publishRun, runKeys, unpublishRun } from "@/api/queries";
import { ErrorNotice } from "@/components/ui";
import { useSession } from "@/hooks/useSession";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { ScheduleRun } from "@/types/api";

/**
 * A schedule is a private draft until it is published; only then do staff see
 * their shifts. Publishing one withdraws any other, so staff always see one.
 */
export function PublishBar({ run }: { run: ScheduleRun }) {
  const { t, formatDate } = useI18n();
  const { capabilities } = useSession();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [notify, setNotify] = useState(true);
  const [notified, setNotified] = useState<number | null>(null);
  const published = Boolean(run.published_at);

  const toggle = useMutation({
    mutationFn: () =>
      published ? unpublishRun(run.schedule_id) : publishRun(run.schedule_id, notify),
    onSuccess: (result) => {
      setNotified(result.notified);
      toast(result.published_at ? t("toast.published") : t("toast.withdrawn"));
      queryClient.setQueryData<ScheduleRun | null>(runKeys.latest, (current) =>
        current ? { ...current, published_at: result.published_at } : current,
      );
    },
  });

  return (
    <section className="card flex flex-wrap items-center gap-3 print:hidden">
      <span
        className={`badge gap-1 ${
          published
            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
        }`}
      >
        {published ? <Eye className="h-3.5 w-3.5" aria-hidden /> : <EyeOff className="h-3.5 w-3.5" aria-hidden />}
        {published
          ? t("publish.published", { date: formatDate(run.published_at!.slice(0, 10)) })
          : t("publish.draft")}
      </span>
      <span className="text-sm text-slate-500">
        {published ? t("publish.visibleHint") : t("publish.draftHint")}
      </span>

      <div className="ms-auto flex flex-wrap items-center gap-3">
        {!published && capabilities?.email_available && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
            {t("publish.emailStaff")}
          </label>
        )}
        <button
          className={published ? "btn-ghost" : "btn-primary"}
          disabled={toggle.isPending}
          onClick={() => toggle.mutate()}
        >
          {published ? <EyeOff className="h-4 w-4" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
          {published ? t("publish.withdraw") : t("publish.publish")}
        </button>
      </div>
      {notified !== null && (
        <p className="basis-full text-sm text-emerald-700 dark:text-emerald-400">
          {t("publish.notified", { count: notified })}
        </p>
      )}
      {toggle.error ? <ErrorNotice message={errorText(toggle.error, t)} /> : null}
    </section>
  );
}
