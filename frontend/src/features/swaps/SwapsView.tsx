import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useToast } from "@/components/Toasts";
import { runKeys, swapAction, swapConflicts, swapKeys, useSwaps } from "@/api/queries";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { Swap } from "@/types/api";
import { conflictText } from "@/features/dashboard/conflictText";

const OPEN = new Set(["AWAITING_COLLEAGUE", "AWAITING_MANAGER"]);

/** Shift swap requests: the colleague answers first, then a manager decides. */
export function SwapsView() {
  const { t } = useI18n();
  const swaps = useSwaps();

  if (swaps.isLoading) return <Skeleton className="h-32" />;
  const list = swaps.data ?? [];
  if (!list.length) return <EmptyState title={t("swap.empty")} hint={t("swap.emptyHint")} />;

  const open = list.filter((s) => OPEN.has(s.status));
  const settled = list.filter((s) => !OPEN.has(s.status));

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="text-lg font-medium">{t("swap.open")}</h2>
        {open.length ? open.map((s) => <SwapCard key={s.id} swap={s} />) : (
          <p className="text-sm text-slate-500">{t("swap.nothingOpen")}</p>
        )}
      </section>
      {settled.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-medium">{t("swap.settled")}</h2>
          {settled.map((s) => <SwapCard key={s.id} swap={s} />)}
        </section>
      )}
    </div>
  );
}

function SwapCard({ swap }: { swap: Swap }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [acknowledged, setAcknowledged] = useState(false);

  const conflicts = useQuery({
    queryKey: ["swap-conflicts", swap.id],
    enabled: swap.can_decide,
    queryFn: () => swapConflicts(swap.id),
  });

  const act = useMutation({
    mutationFn: (action: "accept" | "decline" | "cancel" | "approve" | "deny") =>
      swapAction(swap.id, action, { acknowledge_conflicts: acknowledged }),
    onSuccess: () => {
      toast(t("toast.swapUpdated"));
      void queryClient.invalidateQueries({ queryKey: swapKeys.all });
      // An approved swap changes the schedule itself.
      void queryClient.invalidateQueries({ queryKey: runKeys.latest });
      void queryClient.invalidateQueries({ queryKey: ["my-shifts"] });
    },
  });

  const found = conflicts.data ?? [];
  const blocked = swap.can_decide && found.length > 0 && !acknowledged;

  return (
    <article className="card space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{swap.from_name}</span>
        <ArrowRight className="h-4 w-4 text-slate-400 rtl:rotate-180" aria-hidden />
        <span className="font-medium">{swap.to_name}</span>
        <span className="text-slate-500">
          {swap.job_name} · {swap.template_name} ·{" "}
          {formatDate(swap.calendar_date, { weekday: "short", day: "numeric", month: "short" })}
        </span>
        <span className="badge ms-auto bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {t(`swap.status.${swap.status}`)}
        </span>
      </div>
      {swap.note && <p className="text-sm text-slate-600 dark:text-slate-400">“{swap.note}”</p>}
      {swap.review_note && <p className="text-xs text-slate-500">{swap.review_note}</p>}

      {swap.can_decide && found.length > 0 && (
        <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <p className="font-medium">{t("edit.conflictsTitle")}</p>
          <ul className="list-disc ps-5">
            {found.map((c) => (
              <li key={c.kind}>
                {conflictText(
                  t,
                  c.kind,
                  {
                    person: swap.to_name,
                    job: swap.job_name,
                    window: swap.template_name,
                    date: formatDate(swap.calendar_date),
                  },
                  c.message,
                )}
              </li>
            ))}
          </ul>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
            {t("swap.approveAnyway")}
          </label>
        </div>
      )}

      {act.error ? <ErrorNotice message={errorText(act.error, t)} /> : null}

      <div className="flex flex-wrap gap-2">
        {swap.can_accept && (
          <>
            <button className="btn-primary" disabled={act.isPending} onClick={() => act.mutate("accept")}>
              {t("swap.accept")}
            </button>
            <button className="btn-ghost" disabled={act.isPending} onClick={() => act.mutate("decline")}>
              {t("swap.decline")}
            </button>
          </>
        )}
        {swap.can_decide && (
          <>
            <button className="btn-primary" disabled={act.isPending || blocked} onClick={() => act.mutate("approve")}>
              {t("swap.approve")}
            </button>
            <button className="btn-ghost" disabled={act.isPending} onClick={() => act.mutate("deny")}>
              {t("swap.deny")}
            </button>
          </>
        )}
        {swap.can_cancel && (
          <button className="btn-ghost" disabled={act.isPending} onClick={() => act.mutate("cancel")}>
            {t("swap.cancel")}
          </button>
        )}
      </div>
    </article>
  );
}
