import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, Clock } from "lucide-react";
import { downloadExport } from "@/api/client";
import { myShiftsKey, fetchMyShifts } from "@/api/queries";
import { EmptyState, Skeleton } from "@/components/ui";
import { useI18n } from "@/i18n";
import { shiftWindow } from "@/lib/schedule";
import { groupByDate, nextShift } from "@/lib/myShifts";

/** What a staff member sees: their own shifts from the published schedule. */
export function MyShiftsView() {
  const { t, formatDate } = useI18n();
  const shifts = useQuery({ queryKey: myShiftsKey, queryFn: fetchMyShifts });

  const days = useMemo(() => groupByDate(shifts.data?.assignments ?? []), [shifts.data]);
  const upcoming = useMemo(() => nextShift(shifts.data?.assignments ?? [], new Date()), [shifts.data]);

  if (shifts.isLoading) return <Skeleton className="h-40" />;

  if (!shifts.data?.schedule_id) {
    return <EmptyState title={t("mine.notPublished")} hint={t("mine.notPublishedHint")} />;
  }
  if (!days.length) {
    return <EmptyState title={t("mine.none")} hint={t("mine.noneHint")} />;
  }

  return (
    <div className="space-y-4">
      {upcoming && (
        <section className="card flex items-center gap-3 border-emerald-300 dark:border-emerald-900">
          <Clock className="h-5 w-5 text-emerald-600" aria-hidden />
          <div>
            <div className="label mb-0">{t("mine.next")}</div>
            <div className="text-base font-medium">
              {formatDate(upcoming.calendar_date, { weekday: "long", day: "numeric", month: "short" })}{" "}
              <span dir="ltr" className="tabular-nums">{shiftWindow(upcoming)}</span>
            </div>
            <div className="text-sm text-slate-500">
              {upcoming.job_name} · {upcoming.template_name}
            </div>
          </div>
        </section>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">{t("mine.title")}</h2>
        <button
          className="btn-ghost text-sm"
          onClick={() => downloadExport(shifts.data!.schedule_id!, "ics")}
        >
          <CalendarPlus className="h-4 w-4" aria-hidden />
          {t("mine.addToCalendar")}
        </button>
      </div>

      <ul className="space-y-2">
        {days.map(([date, list]) => (
          <li key={date} className="card">
            <div className="label">
              {formatDate(date, { weekday: "long", day: "numeric", month: "long" })}
            </div>
            <ul className="space-y-1">
              {list.map((a) => (
                <li key={`${a.job_id}-${a.template_id}`} className="flex items-baseline gap-3 text-sm">
                  <span dir="ltr" className="w-28 shrink-0 tabular-nums font-medium">{shiftWindow(a)}</span>
                  <span>{a.job_name}</span>
                  <span className="text-slate-500">{a.template_name}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}
