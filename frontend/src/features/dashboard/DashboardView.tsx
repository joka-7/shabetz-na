import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CalendarRange, Play } from "lucide-react";
import { ApiError } from "@/api/client";
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
import type { Division, ScheduleRun } from "@/types/api";

function isoDaysFromToday(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

export function DashboardView() {
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
              <label className="label" htmlFor="start-date">From</label>
              <input
                id="start-date"
                className="input w-44"
                type="date"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="end-date">To</label>
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
              {generate.isPending ? "Generating…" : "Generate schedule"}
            </button>
            {run && <ExportBar scheduleId={run.schedule_id} />}
          </div>

          {generate.error ? (
            <div className="mt-3">
              <ErrorNotice
                message={
                  generate.error instanceof ApiError
                    ? generate.error.message
                    : "The schedule could not be generated"
                }
              />
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
          title="No schedule generated yet"
          hint={
            can.generate(user)
              ? "Pick a date range and generate one."
              : "A scheduler needs to generate one before your shifts appear."
          }
        />
      )}

      {run && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <StatCard label="Shifts assigned" value={run.summary.total_assignments} />
            <StatCard
              label="Staff used"
              value={`${run.summary.people_used}/${run.summary.total_people}`}
              hint={`${utilizationPercent(run)}% utilisation`}
            />
            <StatCard
              label="Understaffed"
              value={run.summary.understaffed_shift_count}
              tone={run.summary.understaffed_shift_count > 0 ? "danger" : "default"}
              hint={run.summary.understaffed_shift_count > 0 ? "needs attention" : "fully covered"}
            />
            {/* Borrowing is how the rotation stays honest when a division is
                short; it is a cost to see, not a gap to fix. */}
            <StatCard
              label="Borrowed staff"
              value={run.summary.division_fallback_count}
              tone={run.summary.division_fallback_count > 0 ? "warn" : "default"}
              hint="from outside the division on duty"
            />
            <StatCard
              label="Warnings"
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
                {option === "table" ? "Table" : "Timeline"}
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
  const days = rotationByDay(run, divisions);
  if (!days.length) return null;

  return (
    <section className="card">
      <div className="mb-2 flex items-center gap-2">
        <CalendarRange className="h-4 w-4 text-slate-400" aria-hidden />
        <h2 className="label mb-0">Division on duty</h2>
      </div>
      <div className="flex flex-wrap gap-1">
        {days.map((day) => (
          <div
            key={day.date}
            className="rounded border border-slate-200 px-2 py-1 text-xs dark:border-slate-800"
            title={`${day.date}: ${day.divisionName}`}
          >
            <div className="tabular-nums text-slate-400">{day.date.slice(5)}</div>
            <div className="font-medium">{day.divisionName}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
