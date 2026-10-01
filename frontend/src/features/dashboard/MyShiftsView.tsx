import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2, Repeat } from "lucide-react";
import { downloadExport } from "@/api/client";
import { fetchMyShifts, myShiftsKey } from "@/api/queries";
import { Avatar, EmptyState, Skeleton } from "@/components/ui";
import { SwapDialog } from "@/features/swaps/SwapDialog";
import { useSession } from "@/hooks/useSession";
import { useI18n } from "@/i18n";
import { startsIn, nextShift } from "@/lib/myShifts";
import { shiftWindow } from "@/lib/schedule";
import type { Assignment } from "@/types/api";

/** One tone per window name, so "morning" and "night" read differently at a glance. */
const WINDOW_TONES = [
  "bg-teal-100 text-teal-900 dark:bg-teal-950 dark:text-teal-300",
  "bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-300",
  "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-300",
];

/** What a staff member sees: their own shifts from the published schedule. */
export function MyShiftsView() {
  const { t, tn, formatDate } = useI18n();
  const { user, project } = useSession();
  const shifts = useQuery({ queryKey: myShiftsKey, queryFn: fetchMyShifts });
  const [swapping, setSwapping] = useState<Assignment | null>(null);
  const [sent, setSent] = useState(false);

  const now = useMemo(() => new Date(), []);
  const all = shifts.data?.assignments ?? [];
  const upcoming = useMemo(() => nextShift(all, now), [all, now]);
  const rest = useMemo(
    () =>
      all
        .filter((a) => a !== upcoming && a.calendar_date >= (upcoming?.calendar_date ?? ""))
        .sort((a, b) => a.calendar_date.localeCompare(b.calendar_date) || a.start_abs - b.start_abs),
    [all, upcoming],
  );

  // Windows get a colour by their order of first appearance.
  const windowTone = useMemo(() => {
    const names = [...new Set(all.map((a) => a.template_name))];
    return new Map(names.map((n, i) => [n, WINDOW_TONES[i % WINDOW_TONES.length]!]));
  }, [all]);

  if (shifts.isLoading) return <Skeleton className="h-40" />;

  if (!shifts.data?.schedule_id) {
    return <EmptyState title={t("mine.notPublished")} hint={t("mine.notPublishedHint")} />;
  }
  if (!all.length) {
    return <EmptyState title={t("mine.none")} hint={t("mine.noneHint")} />;
  }

  const calendar = () => downloadExport(shifts.data!.schedule_id!, "ics");
  const offer = (a: Assignment) => {
    setSent(false);
    setSwapping(a);
  };

  const when = (a: Assignment): string => {
    const s = startsIn(a, now);
    if (s.kind === "running") return t("mine.running");
    if (s.kind === "later") return t("mine.startsIn", { time: `${s.hours}h ${s.minutes}m` });
    if (s.days === 1) return t("mine.tomorrow");
    return formatDate(a.calendar_date, { weekday: "short", day: "numeric", month: "short" });
  };

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <section className="card flex items-center gap-3">
        <Avatar name={user?.full_name ?? "?"} id={user?.id ?? 0} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-base font-semibold">{user?.full_name}</div>
          <div className="truncate text-sm text-slate-500">{project?.name}</div>
        </div>
        <span className="badge shrink-0 gap-1 bg-emerald-100 px-2 py-1 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
          {t("mine.published")}
        </span>
      </section>

      {upcoming && (
        <section className="rounded-xl border border-teal-300 bg-teal-100 p-4 shadow-sm dark:border-teal-800 dark:bg-teal-950">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="badge gap-1.5 bg-teal-900 px-2 py-1 text-teal-50 dark:bg-teal-700">
              <span className="h-1.5 w-1.5 rounded-full bg-teal-300" aria-hidden />
              {t("mine.upNext")}
            </span>
            <span className="text-sm font-semibold text-teal-900 dark:text-teal-200">{when(upcoming)}</span>
          </div>
          <div className="text-3xl font-bold tabular-nums tracking-tight text-teal-950 dark:text-teal-50" dir="ltr">
            {shiftWindow(upcoming)}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-teal-900 dark:text-teal-100">{upcoming.job_name}</span>
            <span className="badge bg-white/70 text-teal-900 dark:bg-teal-900 dark:text-teal-100">
              {upcoming.template_name}
            </span>
          </div>
          <div className="mt-1 text-sm text-teal-800 dark:text-teal-300">
            {formatDate(upcoming.calendar_date, { weekday: "long", day: "numeric", month: "long" })}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button
              className="btn min-h-11 justify-center whitespace-nowrap bg-teal-900 px-2 text-[13px] text-white hover:bg-teal-800 dark:bg-teal-700"
              onClick={calendar}
            >
              <CalendarPlus className="h-4 w-4" aria-hidden />
              {t("mine.addToCalendar")}
            </button>
            <button className="btn min-h-11 justify-center whitespace-nowrap bg-white px-2 text-[13px] text-teal-900 hover:bg-teal-50 dark:bg-teal-900 dark:text-teal-50" onClick={() => offer(upcoming)}>
              <Repeat className="h-4 w-4" aria-hidden />
              {t("swap.offer")}
            </button>
          </div>
        </section>
      )}

      {sent && (
        <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
          {t("swap.sent")}
        </p>
      )}

      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">{t("mine.upcoming")}</h2>
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {tn("mine.count", all.length)}
        </span>
      </div>

      <ul className="space-y-3">
        {rest.map((a) => (
          <li key={`${a.job_id}-${a.template_id}-${a.calendar_date}`} className="card space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <div>
                <span className="text-base font-semibold">
                  {formatDate(a.calendar_date, { weekday: "long" })}
                </span>{" "}
                <span className="text-sm text-slate-500">
                  {formatDate(a.calendar_date, { day: "numeric", month: "short" })}
                </span>
              </div>
              <span className={`badge px-2 py-1 ${windowTone.get(a.template_name)}`}>{a.template_name}</span>
            </div>
            <div className="text-2xl font-bold tabular-nums text-indigo-700 dark:text-indigo-300" dir="ltr">
              {shiftWindow(a)}
            </div>
            <div className="text-sm">{a.job_name}</div>
            <div className="grid grid-cols-2 gap-2 pt-1">
              <button className="btn-ghost min-h-11 justify-center whitespace-nowrap px-2 text-[13px]" onClick={calendar}>
                <CalendarPlus className="h-4 w-4" aria-hidden />
                {t("mine.addToCalendar")}
              </button>
              <button className="btn-ghost min-h-11 justify-center whitespace-nowrap px-2 text-[13px]" onClick={() => offer(a)}>
                <Repeat className="h-4 w-4" aria-hidden />
                {t("swap.offer")}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {swapping && (
        <SwapDialog
          shift={swapping}
          onClose={() => setSwapping(null)}
          onSent={() => {
            setSwapping(null);
            setSent(true);
          }}
        />
      )}
    </div>
  );
}
