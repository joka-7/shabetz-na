import { useMemo } from "react";
import { EmptyState } from "@/components/ui";
import { useI18n } from "@/i18n";
import { buildTimeline, clockTime } from "@/lib/schedule";
import type { Division, ScheduleRun } from "@/types/api";

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
}: {
  run: ScheduleRun;
  divisions: Division[];
}) {
  const { t, formatDate } = useI18n();
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
                        className="relative h-6 flex-1 rounded bg-slate-100 dark:bg-slate-800"
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
                              className={`h-4 min-w-1.5 flex-1 rounded-sm ${jobTone.get(assignment.job_id)} ${
                                assignment.is_division_fallback
                                  ? "ring-1 ring-amber-500"
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
                            />
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

      <p className="text-xs text-slate-500">{t("timeline.legend")}</p>
    </section>
  );
}
