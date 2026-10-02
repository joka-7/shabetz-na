import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Lock, Pencil, Plus } from "lucide-react";
import { ApiError } from "@/api/client";
import { swapShifts, useTemplates } from "@/api/queries";
import { divisionChip, EmptyState, ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import { clockTime } from "@/lib/schedule";
import { buildMatrix } from "@/lib/matrix";
import type { Assignment, Division, ScheduleRun, SlotRef } from "@/types/api";

/** One tone per window, so a row's left edge says "morning", "evening" or "night" at a glance. */
const WINDOW_EDGE = ["border-s-sky-500", "border-s-indigo-500", "border-s-amber-500", "border-s-teal-500"];

/**
 * The schedule as a grid: a row for each job window, a column for each day.
 *
 * A gap is drawn as a dashed red cell where the person should be, so what is
 * missing is as visible as what is there. People can be dragged onto each
 * other to trade shifts.
 */
export function TimelineGantt({
  run,
  divisions,
  onChanged,
  onFix,
}: {
  run: ScheduleRun;
  divisions: Division[];
  /** Present only for roles that may change a schedule; enables drag to swap. */
  onChanged?: (run: ScheduleRun) => void;
  onFix?: (slot: SlotRef) => void;
}) {
  const { t, tn, formatDate } = useI18n();
  const [dragging, setDragging] = useState<Assignment | null>(null);
  const [pending, setPending] = useState<{ a: Assignment; b: Assignment; message: string } | null>(
    null,
  );

  const { data: templates } = useTemplates();
  const matrix = useMemo(
    () => buildMatrix(run, new Map((templates ?? []).map((tpl) => [tpl.id, tpl]))),
    [run, templates],
  );
  const divisionName = useMemo(() => new Map(divisions.map((d) => [d.id, d.name])), [divisions]);

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

  if (!matrix.rows.length) return <EmptyState title={t("timeline.empty")} />;

  const same = (x: Assignment, y: Assignment) =>
    x.person_id === y.person_id && x.template_id === y.template_id && x.calendar_date === y.calendar_date;

  return (
    <section className="card space-y-3 p-0">
      <div className="flex flex-wrap items-center gap-3 px-4 pt-4">
        <h2 className="text-base font-semibold">{t("timeline.matrixTitle")}</h2>
        <p className="text-xs text-slate-500">{t("timeline.matrixHint")}</p>
        <div className="ms-auto flex flex-wrap gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full ring-2 ring-amber-500" aria-hidden />
            {t("timeline.borrowedKey")}
          </span>
          <span className="flex items-center gap-1">
            <Lock className="h-3 w-3" aria-hidden />
            {t("timeline.pinnedKey")}
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm border border-dashed border-red-500 bg-red-50 dark:bg-red-950" aria-hidden />
            {t("timeline.gapKey")}
          </span>
        </div>
      </div>

      <div className="max-h-[36rem] overflow-auto">
        <table className="w-max min-w-full border-separate border-spacing-x-1.5 border-spacing-y-1.5 px-2 pb-3">
          <thead>
            <tr>
              <th className="sticky start-0 top-0 z-20 min-w-44 bg-white px-2 text-start dark:bg-slate-800">
                <span className="th px-0">{t("timeline.slot")}</span>
              </th>
              {matrix.dates.map((date) => (
                <th
                  key={date}
                  className="sticky top-0 z-10 min-w-36 rounded-lg bg-slate-100 px-2 py-1.5 text-center text-xs font-semibold dark:bg-slate-900"
                >
                  {formatDate(date, { weekday: "short", day: "numeric", month: "short" })}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row, index) => (
              <tr key={row.key}>
                <th
                  scope="row"
                  className={`sticky start-0 z-10 rounded-lg border border-s-4 border-slate-200 bg-white px-3 py-2 text-start align-top dark:border-slate-700 dark:bg-slate-800 ${WINDOW_EDGE[index % WINDOW_EDGE.length]}`}
                >
                  <div className="text-sm font-semibold">{row.templateName}</div>
                  <div className="text-xs text-slate-500">{row.jobName}</div>
                  <div className="mt-0.5 text-xs tabular-nums text-slate-500" dir="ltr">
                    {clockTime(row.start)}–{clockTime(row.end)}
                  </div>
                  <div
                    className={`mt-1 inline-flex items-center gap-1 text-[11px] font-semibold ${
                      row.gaps > 0
                        ? "text-red-600 dark:text-red-400"
                        : "text-emerald-600 dark:text-emerald-400"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${row.gaps > 0 ? "bg-red-500" : "bg-emerald-500"}`}
                      aria-hidden
                    />
                    {row.gaps > 0 ? tn("timeline.gaps", row.gaps) : t("timeline.covered")}
                  </div>
                </th>
                {matrix.dates.map((date) => {
                  const cell = row.cells[date];
                  return (
                    <td key={date} className="align-top">
                      <div className="flex flex-col gap-1">
                        {(cell?.people ?? []).map((a) => (
                          <div
                            key={a.person_id}
                            draggable={Boolean(onChanged)}
                            onDragStart={() => setDragging(a)}
                            onDragEnd={() => setDragging(null)}
                            onDragOver={(event) => {
                              if (dragging && dragging.person_id !== a.person_id) event.preventDefault();
                            }}
                            onDrop={(event) => {
                              event.preventDefault();
                              if (dragging && dragging.person_id !== a.person_id) {
                                swap.mutate({ a: dragging, b: a, acknowledge: false });
                              }
                              setDragging(null);
                            }}
                            title={[
                              a.person_name,
                              a.job_name,
                              `${clockTime(a.start_abs)}–${clockTime(a.end_abs)}`,
                              divisionName.get(a.division_id) ?? "",
                              a.is_division_fallback ? t("timeline.borrowed") : "",
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                            className={`rounded-lg border px-2 py-1 text-xs ${divisionChip(a.division_id)} ${
                              a.is_division_fallback ? "ring-2 ring-amber-500" : ""
                            } ${onChanged ? "cursor-grab active:cursor-grabbing" : ""} ${
                              dragging && same(dragging, a) ? "opacity-40" : ""
                            }`}
                          >
                            <div className="flex items-center gap-1">
                              <span className="truncate font-semibold">{a.person_name}</span>
                              <span className="ms-auto flex shrink-0 items-center gap-0.5">
                                {a.is_manual && <Pencil className="h-3 w-3 opacity-70" aria-label={t("edit.manual")} />}
                                {a.is_locked && <Lock className="h-3 w-3 opacity-70" aria-label={t("edit.lockedHint")} />}
                              </span>
                            </div>
                            <div className="truncate text-[10px] opacity-75">
                              {divisionName.get(a.division_id) ?? ""}
                            </div>
                          </div>
                        ))}
                        {Array.from({ length: cell?.missing ?? 0 }, (_, i) => (
                          <button
                            key={`gap-${i}`}
                            type="button"
                            disabled={!onFix}
                            onClick={() =>
                              onFix?.({ job_id: row.jobId, template_id: row.templateId, calendar_date: date })
                            }
                            className="flex items-center gap-1 rounded-lg border border-dashed border-red-400 bg-red-50 px-2 py-1.5 text-start text-xs font-medium text-red-700 enabled:hover:bg-red-100 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
                          >
                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
                            <span className="flex-1">{t("timeline.hole")}</span>
                            {onFix && <Plus className="h-3.5 w-3.5" aria-hidden />}
                          </button>
                        ))}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pending && (
        <div className="mx-4 space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
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
      {swap.error && !pending ? (
        <div className="px-4">
          <ErrorNotice message={errorText(swap.error, t)} />
        </div>
      ) : null}

      <p className="px-4 pb-4 text-xs text-slate-500">{onChanged ? t("timeline.dragHint") : ""}</p>
    </section>
  );
}
