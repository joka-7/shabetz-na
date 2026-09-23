import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CalendarRange, Play } from "lucide-react";
import { generateSchedule, useDivisions } from "@/api/queries";
import { can, useSession } from "@/hooks/useSession";
import {
  EmptyState,
  ErrorNotice,
  Skeleton,
  StatCard,
} from "@/components/ui";
import {
  blockingWarnings,
  rotationByDay,
  utilizationPercent,
} from "@/lib/schedule";
import { AssignmentsTable } from "./AssignmentsTable";
import { TimelineGantt } from "./TimelineGantt";
import { WarningsPanel } from "./WarningsPanel";
import { ExportBar } from "@/features/export/ExportBar";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { Division, ScheduleRun } from "@/types/api";

/** A local calendar date; toISOString would give UTC's, a day off near midnight. */
function isoDaysFromToday(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function DashboardView() {
  const { t } = useI18n();
  const { user } = useSession();
  const { data: divisions } = useDivisions();
  const [start, setStart] = useState(isoDaysFromToday(0));
  const [end, setEnd] = useState(isoDaysFromToday(13));
  const [view, setView] = useState<"table" | "timeline">("table");

  const generate = useMutation<ScheduleRun, unknown, void>({
    mutationFn: () => generateSchedule(start, end),
  });
  const run = generate.data;

  return (
    <div className="space-y-4">
      {can.generate(user) && (
        <section className="card">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="label" htmlFor="start-date">{t("dashboard.from")}</label>
              <input
                id="start-date"
                className="input w-44"
                type="date"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="end-date">{t("dashboard.to")}</label>
              <input
                id="end-date"
                className="input w-44"
                type="date"
                value={end}
                onChange={(event) => setEnd(event.target.value)}
              />
            </div>
            <button
              className="btn-primary"
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
            >
              <Play className="h-4 w-4" aria-hidden />
              {generate.isPending ? t("dashboard.generating") : t("dashboard.generate")}
            </button>
            {run && <ExportBar scheduleId={run.schedule_id} />}
          </div>

          {generate.error ? (
            <div className="mt-3">
              <ErrorNotice message={errorText(generate.error, t)} />
            </div>
          ) : null}
        </section>
      )}

      {generate.isPending && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-20" />
          ))}
        </div>
      )}

      {!run && !generate.isPending && (
        <EmptyState
          title={t("dashboard.emptyTitle")}
          hint={can.generate(user) ? t("dashboard.emptyHint") : t("dashboard.emptyHintStaff")}
        />
      )}

      {run && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <StatCard label={t("stat.shifts")} value={run.summary.total_assignments} />
            <StatCard
              label={t("stat.staffUsed")}
              value={`${run.summary.people_used}/${run.summary.total_people}`}
              hint={t("stat.utilisation", { percent: utilizationPercent(run) })}
            />
            <StatCard
              label={t("stat.understaffed")}
              value={run.summary.understaffed_shift_count}
              tone={run.summary.understaffed_shift_count > 0 ? "danger" : "default"}
              hint={
                run.summary.understaffed_shift_count > 0
                  ? t("stat.needsAttention")
                  : t("stat.fullyCovered")
              }
            />
            {/* Borrowing is how the rotation stays honest when a division is
                short; it is a cost to see, not a gap to fix. */}
            <StatCard
              label={t("stat.borrowed")}
              value={run.summary.division_fallback_count}
              tone={run.summary.division_fallback_count > 0 ? "warn" : "default"}
              hint={t("stat.borrowedHint")}
            />
            <StatCard
              label={t("stat.warnings")}
              value={blockingWarnings(run.warnings).length}
              tone={blockingWarnings(run.warnings).length > 0 ? "warn" : "default"}
            />
          </div>

          <RotationStrip run={run} divisions={divisions ?? []} />

          <div className="flex gap-1">
            {(["table", "timeline"] as const).map((option) => (
              <button
                key={option}
                onClick={() => setView(option)}
                aria-current={view === option ? "true" : undefined}
                className={`btn text-sm ${
                  view === option
                    ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                    : "border border-slate-300 dark:border-slate-700"
                }`}
              >
                {option === "table" ? t("dashboard.table") : t("timeline.title")}
              </button>
            ))}
          </div>

          {view === "table" ? (
            <AssignmentsTable run={run} divisions={divisions ?? []} />
          ) : (
            <TimelineGantt run={run} divisions={divisions ?? []} />
          )}

          <WarningsPanel warnings={run.warnings} />
        </>
      )}
    </div>
  );
}

function RotationStrip({
  run,
  divisions,
}: {
  run: ScheduleRun;
  divisions: Division[];
}) {
  const { t, formatDate } = useI18n();
  const days = rotationByDay(run, divisions);
  if (!days.length) return null;

  return (
    <section className="card">
      <div className="mb-2 flex items-center gap-2">
        <CalendarRange className="h-4 w-4 text-slate-400" aria-hidden />
        <h2 className="label mb-0">{t("dashboard.onDuty")}</h2>
      </div>
      <div className="flex flex-wrap gap-1">
        {days.map((day) => {
          const name = day.divisionId === null ? t("dashboard.rotationOff") : day.divisionName;
          return (
          <div
            key={day.date}
            className="rounded border border-slate-200 px-2 py-1 text-xs dark:border-slate-800"
            title={`${day.date}: ${name}`}
          >
            <div className="tabular-nums text-slate-400">
              {formatDate(day.date, { weekday: "short", day: "numeric", month: "numeric" })}
            </div>
            <div className="font-medium">{name}</div>
          </div>
          );
        })}
      </div>
    </section>
  );
}
