import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, Printer, UserCheck, X } from "lucide-react";
import { api } from "@/api/client";
import { attendanceKey, useAttendance, useDivisions, useJobs, useLatestRun } from "@/api/queries";
import { ShareBox } from "@/components/ShareBox";
import { DivisionBadge, EmptyState, ErrorNotice, Skeleton } from "@/components/ui";
import { can, useSession } from "@/hooks/useSession";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import { awayMap, reportText, standing, summarize, type ReportLabels } from "@/lib/attendance";
import { buildDayBoard } from "@/lib/dayBoard";
import { addDaysIso, todayIso } from "@/lib/dates";
import type { AttendanceRow, AttendanceStatus } from "@/types/api";

/**
 * Who is here today. Editors mark people present or absent; everyone who can
 * see the schedule sees the day, and a status report is one tap away.
 */
export function AttendanceView() {
  const { t, formatDate } = useI18n();
  const { project } = useSession();
  const canMark = can.generate(project);
  const queryClient = useQueryClient();
  const [date, setDate] = useState(todayIso());
  const [search, setSearch] = useState("");
  const [division, setDivision] = useState<number | "all">("all");

  const { data: rows, isLoading } = useAttendance(date);
  const { data: divisions = [] } = useDivisions();
  const { data: jobs = [] } = useJobs();
  const latest = useLatestRun(true);

  const mark = useMutation({
    mutationFn: (body: { person_id: number; status: AttendanceStatus | null; note?: string | null }) =>
      api.put<AttendanceRow[]>("/api/attendance", { ...body, calendar_date: date }),
    onSuccess: (updated) => queryClient.setQueryData(attendanceKey(date), updated),
  });
  const markAll = useMutation({
    mutationFn: () =>
      api.post<AttendanceRow[]>("/api/attendance/bulk", { calendar_date: date, status: "PRESENT" }),
    onSuccess: (updated) => queryClient.setQueryData(attendanceKey(date), updated),
  });

  const all = useMemo(() => rows ?? [], [rows]);
  const labels = useMemo(
    () => ({ absent: t("attendance.absent"), leave: t("attendance.onLeave") }),
    [t],
  );
  const counts = summarize(all);
  const shown = all.filter(
    (row) =>
      (division === "all" || row.division_id === division) &&
      row.full_name.toLowerCase().includes(search.trim().toLowerCase()),
  );

  const board = useMemo(
    () => buildDayBoard(date, latest.data?.assignments ?? [], jobs, awayMap(all, labels)),
    [date, latest.data, jobs, all, labels],
  );
  const dateLabel = formatDate(date, { weekday: "long", day: "numeric", month: "numeric" });
  const report: ReportLabels = {
    heading: (d) => t("report.heading", { date: d }),
    totals: (s) =>
      t("report.totals", {
        total: s.total,
        present: s.present,
        absent: s.absent,
        leave: s.leave,
        unmarked: s.unmarked,
      }),
    absent: t("report.absent"),
    leave: t("report.leave"),
    unmarked: t("report.unmarked"),
    gap: (shift, job, count) => t("report.gap", { shift, job, count }),
    gaps: t("report.gaps"),
    allCovered: t("report.allCovered"),
  };
  const text = reportText(dateLabel, all, board, report);

  const error = mark.error ?? markAll.error;

  return (
    <div className="space-y-4">
      <div className="print:hidden">
        <h1 className="text-2xl font-bold tracking-tight">{t("attendance.title")}</h1>
        <p className="text-sm text-slate-500">{t("attendance.subtitle")}</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem] print:hidden">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost p-1.5" onClick={() => setDate(addDaysIso(date, -1))} aria-label={t("board.prevDay")}>
              <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />
            </button>
            <input
              className="input w-44"
              type="date"
              value={date}
              onChange={(event) => event.target.value && setDate(event.target.value)}
              aria-label={t("attendance.date")}
            />
            <button className="btn-ghost p-1.5" onClick={() => setDate(addDaysIso(date, 1))} aria-label={t("board.nextDay")}>
              <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
            </button>
            <button className="btn-ghost text-sm" onClick={() => setDate(todayIso())} disabled={date === todayIso()}>
              {t("attendance.today")}
            </button>
            {canMark && (
              <button
                className="btn-primary ms-auto text-sm"
                onClick={() => markAll.mutate()}
                disabled={markAll.isPending || counts.unmarked + counts.leave === 0}
              >
                <UserCheck className="h-4 w-4" aria-hidden />
                {t("attendance.markAllPresent")}
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-2 text-xs">
            <Chip tone="emerald" label={t("attendance.present")} value={counts.present} />
            <Chip tone="red" label={t("attendance.absent")} value={counts.absent} />
            <Chip tone="amber" label={t("attendance.onLeave")} value={counts.leave} />
            <Chip tone="slate" label={t("attendance.unmarked")} value={counts.unmarked} />
          </div>

          <div className="flex flex-wrap gap-2">
            <input
              className="input w-52"
              placeholder={t("attendance.search")}
              aria-label={t("attendance.search")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <select
              className="input w-auto"
              value={division}
              onChange={(event) => setDivision(event.target.value === "all" ? "all" : Number(event.target.value))}
              aria-label={t("attendance.allDivisions")}
            >
              <option value="all">{t("attendance.allDivisions")}</option>
              {divisions.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          {!canMark && <p className="text-xs text-slate-500">{t("attendance.readOnly")}</p>}
          {error ? <ErrorNotice message={errorText(error, t)} /> : null}

          {isLoading ? (
            <Skeleton className="h-40" />
          ) : all.length === 0 ? (
            <EmptyState title={t("attendance.empty")} />
          ) : (
            <ul className="card divide-y divide-slate-100 p-0 dark:divide-slate-700">
              {shown.map((row) => (
                <PersonRow
                  key={`${date}-${row.person_id}`}
                  row={row}
                  divisionName={divisions.find((d) => d.id === row.division_id)?.name}
                  canMark={canMark}
                  busy={mark.isPending}
                  onMark={(status, note) => mark.mutate({ person_id: row.person_id, status, note })}
                />
              ))}
            </ul>
          )}
        </div>

        <aside className="card h-fit space-y-3 xl:sticky xl:top-4">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold">{t("report.title")}</h2>
            <button className="btn-ghost ms-auto text-sm" onClick={() => window.print()}>
              <Printer className="h-4 w-4" aria-hidden />
              {t("report.print")}
            </button>
          </div>
          <ShareBox text={text} label={t("report.title")} />
        </aside>
      </div>

      {/* On paper: just the report. */}
      <pre className="hidden whitespace-pre-wrap font-sans text-sm text-black print:block">{text}</pre>
    </div>
  );
}

const TONES = {
  emerald: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  red: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  amber: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  slate: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

function Chip({ tone, label, value }: { tone: keyof typeof TONES; label: string; value: number }) {
  return (
    <span className={`badge gap-1.5 ${TONES[tone]}`}>
      <span className="tabular-nums font-semibold">{value}</span>
      {label}
    </span>
  );
}

function PersonRow({
  row,
  divisionName,
  canMark,
  busy,
  onMark,
}: {
  row: AttendanceRow;
  divisionName: string | undefined;
  canMark: boolean;
  busy: boolean;
  onMark: (status: AttendanceStatus | null, note?: string | null) => void;
}) {
  const { t } = useI18n();
  const [note, setNote] = useState(row.note ?? "");
  const s = standing(row);

  // Pressing the active button again clears the mark, and its reason with it.
  const pick = (status: AttendanceStatus) =>
    row.status === status ? onMark(null) : onMark(status, status === "ABSENT" ? note : null);
  const button = (status: AttendanceStatus, active: boolean, label: string, aria: string, icon: React.ReactNode) => (
    <button
      type="button"
      disabled={!canMark || busy}
      onClick={() => pick(status)}
      aria-pressed={active}
      aria-label={aria}
      title={aria}
      className={`btn min-h-9 gap-1 px-2.5 text-xs ${
        active
          ? status === "PRESENT"
            ? "bg-emerald-600 text-white"
            : "bg-red-600 text-white"
          : "border border-slate-300 dark:border-slate-700"
      }`}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );

  return (
    <li className="flex flex-wrap items-center gap-2 px-3 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{row.full_name}</span>
          {divisionName && <DivisionBadge id={row.division_id} name={divisionName} />}
          {s === "leave" && (
            <span className={`badge ${TONES.amber}`} title={row.leave_reason ?? undefined}>
              {t("attendance.onLeave")}
              {row.leave_reason ? ` · ${row.leave_reason}` : ""}
            </span>
          )}
          {s === "unmarked" && <span className="text-xs text-slate-400">{t("attendance.unmarked")}</span>}
        </div>
        {row.status === "ABSENT" && (
          <input
            className="input mt-1 py-1 text-xs"
            placeholder={t("attendance.reason")}
            aria-label={t("attendance.noteFor", { name: row.full_name })}
            value={note}
            disabled={!canMark}
            maxLength={500}
            onChange={(event) => setNote(event.target.value)}
            onBlur={() => note.trim() !== (row.note ?? "") && onMark("ABSENT", note)}
          />
        )}
      </div>
      <div className="flex gap-1">
        {button("PRESENT", row.status === "PRESENT", t("attendance.present"), t("attendance.markPresent", { name: row.full_name }), <Check className="h-4 w-4" aria-hidden />)}
        {button("ABSENT", row.status === "ABSENT", t("attendance.absent"), t("attendance.markAbsent", { name: row.full_name }), <X className="h-4 w-4" aria-hidden />)}
      </div>
    </li>
  );
}
