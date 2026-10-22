import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Share2 } from "lucide-react";
import { useAttendance, useJobs } from "@/api/queries";
import { ShareBox } from "@/components/ShareBox";
import { EmptyState } from "@/components/ui";
import { useI18n } from "@/i18n";
import { absencesOf, awayMap } from "@/lib/attendance";
import { buildDayBoard, scheduleDates } from "@/lib/dayBoard";
import { daysText, dayText, type ShareLabels } from "@/lib/share";
import type { ScheduleRun } from "@/types/api";

/**
 * The schedule by shift rather than by person: for a day, each shift window
 * with its tasks, who works them, and how many are still missing once those
 * who are away are not counted.
 */
export function ShiftBoardView({ run }: { run: ScheduleRun }) {
  const { t, tn, formatDate } = useI18n();
  const { data: jobs = [] } = useJobs();
  const dates = useMemo(() => scheduleDates(run.assignments), [run.assignments]);
  const [date, setDate] = useState(dates[0] ?? "");
  const [sharing, setSharing] = useState(false);
  const [scope, setScope] = useState<"day" | "all">("day");

  // A new schedule may not cover the day being looked at.
  useEffect(() => {
    if (!dates.includes(date)) setDate(dates[0] ?? "");
  }, [dates, date]);

  const attendance = useAttendance(date, date !== "");
  const absent = t("attendance.absent");
  const leave = t("attendance.onLeave");
  const labels = useMemo(() => ({ absent, leave }), [absent, leave]);
  const rows = useMemo(() => attendance.data ?? [], [attendance.data]);
  const board = useMemo(
    () => buildDayBoard(date, run.assignments, jobs, awayMap(rows, labels)),
    [date, run.assignments, jobs, rows, labels],
  );

  const index = dates.indexOf(date);
  const dateLabel = (iso: string) =>
    formatDate(iso, { weekday: "long", day: "numeric", month: "numeric" });

  const shareLabels: ShareLabels = {
    heading: (d) => t("share.heading", { date: d }),
    away: t("share.away"),
    missing: (n) => tn("share.missing", n),
    noShifts: t("share.noShifts"),
  };
  const text =
    scope === "day"
      ? dayText({ dateLabel: dateLabel(date), board, absences: absencesOf(rows, labels) }, shareLabels)
      : daysText(
          dates.map((d) => ({
            dateLabel: dateLabel(d),
            board: buildDayBoard(d, run.assignments, jobs),
            absences: [],
          })),
          shareLabels,
        );

  if (dates.length === 0) return <EmptyState title={t("board.noShifts")} />;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          className="btn-ghost p-1.5"
          onClick={() => setDate(dates[index - 1]!)}
          disabled={index <= 0}
          aria-label={t("board.prevDay")}
        >
          <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />
        </button>
        <select
          className="input w-auto"
          value={date}
          onChange={(event) => setDate(event.target.value)}
          aria-label={t("board.day")}
        >
          {dates.map((d) => (
            <option key={d} value={d}>{dateLabel(d)}</option>
          ))}
        </select>
        <button
          className="btn-ghost p-1.5"
          onClick={() => setDate(dates[index + 1]!)}
          disabled={index >= dates.length - 1}
          aria-label={t("board.nextDay")}
        >
          <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
        </button>
        <button className="btn-ghost ms-auto text-sm" onClick={() => setSharing((open) => !open)}>
          <Share2 className="h-4 w-4" aria-hidden />
          {t("share.button")}
        </button>
      </div>

      {sharing && (
        <div className="card space-y-3">
          <h3 className="text-sm font-semibold">{t("share.title")}</h3>
          <div className="flex gap-1">
            {(["day", "all"] as const).map((option) => (
              <button
                key={option}
                onClick={() => setScope(option)}
                aria-current={scope === option ? "true" : undefined}
                className={scope === option ? "pill-active" : "pill"}
              >
                {option === "day" ? t("share.scopeDay") : t("share.scopeAll")}
              </button>
            ))}
          </div>
          <ShareBox text={text} label={t("share.title")} />
        </div>
      )}

      {board.length === 0 ? (
        <EmptyState title={t("board.noShifts")} />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {board.map((shift) => (
            <section key={shift.templateId} className="card space-y-2">
              <h3 className="flex items-baseline gap-2 text-base font-semibold">
                {shift.window}
                <span className="text-sm font-normal tabular-nums text-slate-500">
                  {shift.start}–{shift.end}
                </span>
              </h3>
              <ul className="divide-y divide-slate-100 dark:divide-slate-700">
                {shift.jobs.map((job) => (
                  <li key={job.jobId} className="space-y-1 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{job.job}</span>
                      {job.required !== null && (
                        <span className="text-xs tabular-nums text-slate-500">
                          {t("board.of", { have: job.present, need: job.required })}
                        </span>
                      )}
                      {job.missing > 0 && (
                        <span className="badge gap-1 bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300">
                          <AlertTriangle className="h-3 w-3" aria-hidden />
                          {tn("board.missing", job.missing)}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {job.people.map((person) => (
                        <span
                          key={person.id}
                          title={person.away ?? undefined}
                          className={`badge ${
                            person.away === null
                              ? "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200"
                              : "bg-amber-100 text-amber-900 line-through dark:bg-amber-950 dark:text-amber-200"
                          }`}
                        >
                          {person.name}
                          {person.away !== null && (
                            <span className="ms-1 text-[10px] no-underline">({t("board.away")})</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
