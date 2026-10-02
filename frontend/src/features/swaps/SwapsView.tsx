import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Clock, X } from "lucide-react";
import { runKeys, swapAction, swapConflicts, swapKeys, useSwaps } from "@/api/queries";
import { Avatar, EmptyState, ErrorNotice, Skeleton } from "@/components/ui";
import { useToast } from "@/components/Toasts";
import { conflictText } from "@/features/dashboard/conflictText";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { Swap, SwapStatus } from "@/types/api";

const OPEN: SwapStatus[] = ["AWAITING_COLLEAGUE", "AWAITING_MANAGER"];

const STATUS_TONE: Record<SwapStatus, string> = {
  AWAITING_COLLEAGUE: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  AWAITING_MANAGER: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  APPROVED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  DENIED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  DECLINED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  CANCELLED: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
};

type Filter = "ALL" | SwapStatus;
const FILTERS: Filter[] = ["ALL", "AWAITING_COLLEAGUE", "AWAITING_MANAGER", "APPROVED", "DENIED"];

/** Shift swap requests: the colleague answers first, then a manager decides. */
export function SwapsView() {
  const { t, tn } = useI18n();
  const swaps = useSwaps();
  const [filter, setFilter] = useState<Filter>("ALL");

  const list = swaps.data ?? [];
  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: list.length };
    for (const s of list) c[s.status] = (c[s.status] ?? 0) + 1;
    return c;
  }, [list]);
  const open = list.filter((s) => OPEN.includes(s.status)).length;
  const shown = filter === "ALL" ? list : list.filter((s) => s.status === filter);

  if (swaps.isLoading) return <Skeleton className="h-40" />;

  return (
    <div className="space-y-4">
      <section className="card space-y-4 bg-indigo-50/60 dark:bg-slate-800">
        <div>
          <span className="badge bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
            {t("swap.eyebrow")}
          </span>
          <h1 className="mt-2 flex flex-wrap items-center gap-3 text-2xl font-bold tracking-tight">
            {t("swap.title")}
            {open > 0 && (
              <span className="badge rounded-full bg-indigo-600 px-2.5 py-1 text-xs text-white">
                {tn("swap.active", open)}
              </span>
            )}
          </h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{t("swap.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label={t("swap.filter")}>
          {FILTERS.map((f) => (
            <button
              key={f}
              role="tab"
              aria-selected={filter === f}
              className={filter === f ? "pill-active" : "pill bg-white dark:bg-slate-900"}
              onClick={() => setFilter(f)}
            >
              {f === "ALL" ? t("swap.all") : t(`swap.status.${f}`)} ({counts[f] ?? 0})
            </button>
          ))}
        </div>
      </section>

      {!shown.length ? (
        <EmptyState title={t("swap.empty")} hint={t("swap.emptyHint")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((s) => (
            <SwapCard key={s.id} swap={s} />
          ))}
        </div>
      )}
    </div>
  );
}

function Party({ name, id, role, align = "start" }: { name: string; id: number; role: string; align?: "start" | "end" }) {
  return (
    <div className={`flex min-w-0 items-center gap-2 ${align === "end" ? "flex-row-reverse text-end" : ""}`}>
      <Avatar name={name} id={id} />
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold">{name}</div>
        <div className="truncate text-[11px] text-slate-500">{role}</div>
      </div>
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
  const settled = !OPEN.includes(swap.status);

  return (
    <article className="card flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span className={`badge gap-1.5 px-2 py-1 ${STATUS_TONE[swap.status]}`}>
          {swap.status === "APPROVED" ? (
            <Check className="h-3 w-3" aria-hidden />
          ) : (
            <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
          )}
          {t(`swap.status.${swap.status}`)}
        </span>
        <span className="text-xs tabular-nums text-slate-500">#{swap.id}</span>
      </div>

      <div className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 p-2.5 dark:bg-slate-900">
        <Party name={swap.from_name} id={swap.from_person_id} role={t("swap.offeredBy")} />
        <ArrowRight className="h-4 w-4 shrink-0 text-indigo-500 rtl:rotate-180" aria-hidden />
        <Party name={swap.to_name} id={swap.to_person_id} role={t("swap.targetPartner")} align="end" />
      </div>

      <dl className="space-y-1 rounded-lg border border-slate-200 p-2.5 text-sm dark:border-slate-700">
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">{t("table.date")}</dt>
          <dd className="font-medium">
            {formatDate(swap.calendar_date, { weekday: "short", day: "numeric", month: "short" })}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">{t("table.window")}</dt>
          <dd className="font-medium">{swap.template_name}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">{t("table.job")}</dt>
          <dd className="font-medium">{swap.job_name}</dd>
        </div>
      </dl>

      {swap.note && (
        <p className="rounded-lg bg-slate-50 p-2.5 text-sm italic text-slate-600 dark:bg-slate-900 dark:text-slate-400">
          “{swap.note}”
        </p>
      )}
      {swap.review_note && <p className="text-xs text-slate-500">{swap.review_note}</p>}

      {swap.status === "AWAITING_COLLEAGUE" && (
        <p className="flex items-center gap-2 rounded-lg bg-teal-50 p-2.5 text-sm text-teal-800 dark:bg-teal-950 dark:text-teal-300">
          <Clock className="h-4 w-4 shrink-0" aria-hidden />
          {t("swap.waitingFor", { name: swap.to_name })}
        </p>
      )}

      {swap.can_decide && found.length > 0 && (
        <div className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-2.5 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          <p className="font-semibold">{t("edit.conflictsTitle")}</p>
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

      {!settled && (
        <div className="mt-auto flex flex-wrap gap-2 pt-1">
          {swap.can_accept && (
            <>
              <button className="btn-primary" disabled={act.isPending} onClick={() => act.mutate("accept")}>
                <Check className="h-4 w-4" aria-hidden />
                {t("swap.accept")}
              </button>
              <button className="btn-ghost" disabled={act.isPending} onClick={() => act.mutate("decline")}>
                <X className="h-4 w-4" aria-hidden />
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
            <button className="btn-ghost ms-auto" disabled={act.isPending} onClick={() => act.mutate("cancel")}>
              {t("swap.cancel")}
            </button>
          )}
        </div>
      )}
    </article>
  );
}
