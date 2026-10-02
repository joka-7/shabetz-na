import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, Play, Printer, UserPlus } from "lucide-react";
import {
  generateSchedule,
  runKeys,
  setShiftLock,
  useDivisions,
  useLatestRun,
} from "@/api/queries";
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
import { EditShiftDialog, type EditTarget } from "./EditShiftDialog";
import { FairnessTable } from "./FairnessTable";
import { HistoryPanel } from "./HistoryPanel";
import { useToast } from "@/components/Toasts";
import { MyShiftsView } from "./MyShiftsView";
import { PrintGrid } from "./PrintGrid";
import { PublishBar } from "./PublishBar";
import { TimelineGantt } from "./TimelineGantt";
import { WarningsPanel } from "./WarningsPanel";
import { ExportBar } from "@/features/export/ExportBar";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { Assignment, Division, ScheduleRun } from "@/types/api";

/** A local calendar date; toISOString would give UTC's, a day off near midnight. */
function isoDaysFromToday(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function DashboardView() {
  const { t } = useI18n();
  const { project } = useSession();
  const { data: divisions } = useDivisions();
  const [start, setStart] = useState(isoDaysFromToday(0));
  const [end, setEnd] = useState(isoDaysFromToday(13));
  const [view, setView] = useState<"table" | "timeline" | "fairness">("table");

  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [keepLocked, setKeepLocked] = useState(true);
  const canEdit = can.generate(project);

  // The schedule lives on the server, so a reload shows the latest one --
  // including any changes made to it by hand.
  const latest = useLatestRun(canEdit);
  const generate = useMutation<ScheduleRun, unknown, void>({
    mutationFn: () => generateSchedule(start, end, keepLocked),
    onSuccess: (created) => queryClient.setQueryData(runKeys.latest, created),
  });
  const run = latest.data ?? undefined;

  const toggleLock = useMutation({
    mutationFn: (a: Assignment) =>
      setShiftLock(
        run!.schedule_id,
        { job_id: a.job_id, template_id: a.template_id, calendar_date: a.calendar_date },
        a.person_id,
        !a.is_locked,
      ),
    onSuccess: (updated) => queryClient.setQueryData(runKeys.latest, updated),
  });

  const lockedCount = run?.assignments.filter((a) => a.is_locked).length ?? 0;

  const onSaved = (updated: ScheduleRun) => {
    queryClient.setQueryData(runKeys.latest, updated);
    setEditing(null);
    toast(t("toast.changeSaved"));
  };

  // Staff do not plan; they see their own shifts once a schedule is published.
  if (!canEdit) return <MyShiftsView />;

  return (
    <>
    {run && <PrintGrid run={run} projectName={project?.name ?? ""} />}
    <div className="space-y-4 print:hidden">
      {can.generate(project) && (
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
            {lockedCount > 0 && (
              <label className="flex items-center gap-2 pb-2 text-sm">
                <input
                  type="checkbox"
                  checked={keepLocked}
                  onChange={(event) => setKeepLocked(event.target.checked)}
                />
                {t("dashboard.keepLocked", { count: lockedCount })}
              </label>
            )}
            {run && <ExportBar scheduleId={run.schedule_id} />}
          </div>

          {generate.error ? (
            <div className="mt-3">
              <ErrorNotice message={errorText(generate.error, t)} />
            </div>
          ) : null}
        </section>
      )}

      {canEdit && latest.isLoading && !run && <Skeleton className="h-40" />}

      {generate.isPending && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-20" />
          ))}
        </div>
      )}

      {!run && !generate.isPending && !latest.isLoading && (
        <EmptyState
          title={t("dashboard.emptyTitle")}
          hint={can.generate(project) ? t("dashboard.emptyHint") : t("dashboard.emptyHintStaff")}
        />
      )}

      {run && (
        <>
          <PublishBar run={run} />

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

          {/* Wide screens: the schedule on the left, what needs attention and what changed on the right. */}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_21rem]">
            <div className="min-w-0 space-y-4">
              <div className="flex flex-wrap items-center gap-1">
                <div className="flex gap-1 rounded-xl border border-slate-200 bg-slate-100 p-1 dark:border-slate-700 dark:bg-slate-900">
                  {(["table", "timeline", "fairness"] as const).map((option) => (
                    <button
                      key={option}
                      onClick={() => setView(option)}
                      aria-current={view === option ? "true" : undefined}
                      className={view === option ? "pill-active" : "pill"}
                    >
                      {option === "table"
                        ? t("dashboard.table")
                        : option === "timeline"
                          ? t("timeline.title")
                          : t("fairness.title")}
                    </button>
                  ))}
                </div>
                <button className="btn-ghost ms-auto text-sm" onClick={() => window.print()}>
                  <Printer className="h-4 w-4" aria-hidden />
                  {t("dashboard.print")}
                </button>
                {canEdit && (
                  <button className="btn-primary text-sm" onClick={() => setEditing({ kind: "add" })}>
                    <UserPlus className="h-4 w-4" aria-hidden />
                    {t("edit.add")}
                  </button>
                )}
              </div>

              {view === "table" ? (
                <AssignmentsTable
                  run={run}
                  divisions={divisions ?? []}
                  onEdit={canEdit ? (assignment) => setEditing({ kind: "reassign", assignment }) : undefined}
                  onToggleLock={canEdit ? (assignment) => toggleLock.mutate(assignment) : undefined}
                />
              ) : view === "timeline" ? (
                <TimelineGantt
                  run={run}
                  divisions={divisions ?? []}
                  onChanged={canEdit ? onSaved : undefined}
                  onFix={canEdit ? (slot) => setEditing({ kind: "add", slot }) : undefined}
                />
              ) : (
                <FairnessTable run={run} />
              )}
            </div>

            <aside className="min-w-0 space-y-4 xl:sticky xl:top-4 xl:self-start">
              <WarningsPanel
                warnings={run.warnings}
                onFix={
                  canEdit
                    ? (warning) =>
                        setEditing({
                          kind: "add",
                          slot: {
                            job_id: warning.job_id!,
                            template_id: warning.template_id!,
                            calendar_date: warning.calendar_date!,
                          },
                        })
                    : undefined
                }
              />
              {canEdit && <HistoryPanel run={run} />}
            </aside>
          </div>

          {editing && (
            <EditShiftDialog
              run={run}
              target={editing}
              onClose={() => setEditing(null)}
              onSaved={onSaved}
            />
          )}
        </>
      )}
    </div>
    </>
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
