import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { swapShifts } from "@/api/queries";
import { EmptyState, ErrorNotice } from "@/components/ui";
import { ApiError } from "@/api/client";
import { errorText } from "@/i18n/errors";
import { useI18n } from "@/i18n";
import { buildTimeline, clockTime } from "@/lib/schedule";
import type { Assignment, Division, ScheduleRun } from "@/types/api";

const JOB_TONES = [
  "bg-sky-500/80",
  "bg-violet-500/80",
  "bg-teal-500/80",
  "bg-orange-500/80",
  "bg-fuchsia-500/80",
  "bg-lime-600/80",
];

/**
 * Who is on which window, day by day.
 *
 * Windows are positioned against a 24-hour axis rather than laid out in even
 * columns, so overlaps and uncovered stretches are visible where a table would
 * simply list rows.
 */
export function TimelineGantt({
  run,
  divisions,
  onChanged,
}: {
  run: ScheduleRun;
  divisions: Division[];
  /** Present only for roles that may change a schedule; enables drag to swap. */
  onChanged?: (run: ScheduleRun) => void;
}) {
  const { t, formatDate } = useI18n();
  const [dragging, setDragging] = useState<Assignment | null>(null);
  const [pending, setPending] = useState<{ a: Assignment; b: Assignment; message: string } | null>(null);

  const swap = useMutation({
    mutationFn: ({ a, b, acknowledge }: { a: Assignment; b: Assignment; acknowledge: boolean }) =>
      swapShifts(run.schedule_id, a, b, acknowledge),
    onSuccess: (updated) => {
      setPending(null);
      onChanged?.(updated);
    },
    onError: (error, { a, b }) => {
      // A rule would be broken: ask before overriding, rather than refusing outright.
      if (error instanceof ApiError && error.code === "SCHEDULE_CONFLICT") {
        setPending({ a, b, message: error.message });
      }
    },
  });
  const rows = useMemo(() => buildTimeline(run.assignments), [run.assignments]);

  const jobTone = useMemo(() => {
    const ids = [...new Set(run.assignments.map((a) => a.job_id))].sort((a, b) => a - b);
    return new Map(ids.map((id, index) => [id, JOB_TONES[index % JOB_TONES.length]!]));
  }, [run.assignments]);

  const jobNames = useMemo(() => {
    const names = new Map<number, string>();
    for (const assignment of run.assignments) names.set(assignment.job_id, assignment.job_name);
    return names;
  }, [run.assignments]);

  const divisionName = useMemo(
    () => new Map(divisions.map((d) => [d.id, d.name])),
    [divisions],
  );

  if (!rows.length) return <EmptyState title={t("timeline.empty")} />;

  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="label mb-0">{t("timeline.title")}</h2>
        <div className="ms-auto flex flex-wrap gap-2">
          {[...jobTone.entries()].map(([id, tone]) => (
            <span key={id} className="flex items-center gap-1 text-xs text-slate-500">
              <span className={`h-2.5 w-2.5 rounded ${tone}`} aria-hidden />
              {jobNames.get(id)}
            </span>
          ))}
        </div>
      </div>

      {/* The hour axis runs left to right in both languages, like a clock. */}
      <div className="relative ms-24 me-10 h-4" dir="ltr">
        {[0, 6, 12, 18, 24].map((hour) => (
          <span
            key={hour}
            className="absolute -translate-x-1/2 text-[10px] tabular-nums text-slate-400"
            style={{ left: `${(hour / 24) * 100}%` }}
          >
            {String(hour % 24).padStart(2, "0")}
          </span>
        ))}
      </div>

      <div className="max-h-[32rem] space-y-2 overflow-auto">
        {rows.map((row) => (
          <div key={row.date}>
            <div className="mb-1 text-xs font-medium tabular-nums text-slate-500">
              {formatDate(row.date, { weekday: "short", day: "numeric", month: "short" })}
            </div>
            <div className="space-y-0.5">
              {[...row.templates.entries()]
                .sort(
                  ([, a], [, b]) => (a[0]?.start_abs ?? 0) - (b[0]?.start_abs ?? 0),
                )
                .map(([templateId, assignments]) => {
                  const first = assignments[0]!;
                  const dayStart = Math.floor(first.start_abs / 24) * 24;
                  const from = first.start_abs - dayStart;
                  const to = Math.min(24, first.end_abs - dayStart);
                  return (
                    <div key={templateId} className="flex items-center gap-2">
                      <span className="w-24 shrink-0 truncate text-xs text-slate-500">
                        {first.template_name}
                      </span>
                      <div
                        className="relative h-7 flex-1 rounded-lg bg-slate-100 dark:bg-slate-900"
                        dir="ltr"
                      >
                        <div
                          className="absolute inset-y-0 flex items-center gap-0.5 overflow-hidden rounded px-1"
                          style={{
                            left: `${(from / 24) * 100}%`,
                            width: `${(Math.max(0.5, to - from) / 24) * 100}%`,
                          }}
                        >
                          {assignments.map((assignment) => (
                            <span
                              key={`${assignment.person_id}-${assignment.job_id}`}
                              draggable={Boolean(onChanged)}
                              onDragStart={() => setDragging(assignment)}
                              onDragEnd={() => setDragging(null)}
                              onDragOver={(event) => {
                                if (dragging && dragging.person_id !== assignment.person_id) {
                                  event.preventDefault();
                                }
                              }}
                              onDrop={(event) => {
                                event.preventDefault();
                                if (dragging && dragging.person_id !== assignment.person_id) {
                                  swap.mutate({ a: dragging, b: assignment, acknowledge: false });
                                }
                                setDragging(null);
                              }}
                              className={`flex h-5 min-w-1.5 flex-1 items-center overflow-hidden rounded-md ${jobTone.get(assignment.job_id)} ${
                                assignment.is_division_fallback
                                  ? "ring-1 ring-amber-500"
                                  : ""
                              } ${onChanged ? "cursor-grab" : ""} ${
                                dragging?.person_id === assignment.person_id &&
                                dragging.template_id === assignment.template_id &&
                                dragging.calendar_date === assignment.calendar_date
                                  ? "opacity-40"
                                  : ""
                              }`}
                              title={[
                                assignment.person_name,
                                assignment.job_name,
                                `${clockTime(assignment.start_abs)}–${clockTime(assignment.end_abs)}`,
                                divisionName.get(assignment.division_id) ?? "",
                                assignment.is_division_fallback ? t("timeline.borrowed") : "",
                              ]
                                .filter(Boolean)
                                .join(" · ")}
                            >
                              <span className="truncate px-1 text-[10px] font-medium text-white">
                                {assignment.person_name.split(" ")[0]}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                      <span className="w-8 shrink-0 text-end text-xs tabular-nums text-slate-400">
                        {assignments.length}
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>
        ))}
      </div>

      {pending && (
        <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <p className="font-medium">
            {t("timeline.swapBreaks", { a: pending.a.person_name, b: pending.b.person_name })}
          </p>
          <p>{pending.message}</p>
          <div className="flex gap-2">
            <button
              className="btn-primary"
              disabled={swap.isPending}
              onClick={() => swap.mutate({ a: pending.a, b: pending.b, acknowledge: true })}
            >
              {t("timeline.swapAnyway")}
            </button>
            <button className="btn-ghost" onClick={() => setPending(null)}>
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}
      {swap.error && !pending ? <ErrorNotice message={errorText(swap.error, t)} /> : null}

      <p className="text-xs text-slate-500">
        {t("timeline.legend")} {onChanged ? t("timeline.dragHint") : ""}
      </p>
    </section>
  );
}
