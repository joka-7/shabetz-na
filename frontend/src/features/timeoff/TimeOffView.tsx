import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, Plus, X } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, usePeople, useTimeOff } from "@/api/queries";
import { can, useSession } from "@/hooks/useSession";
import { Avatar, EmptyState, Spinner } from "@/components/ui";
import { awayByDay, daysInRequest, monthGrid } from "@/lib/calendar";
import { useI18n } from "@/i18n";
import { MutationError } from "@/features/setup/steps/parts";
import type { TimeOff, TimeOffStatus } from "@/types/api";

const STATUS_TONES: Record<TimeOffStatus, string> = {
  PENDING: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  APPROVED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  DENIED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  CANCELLED: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

export function TimeOffView() {
  const { t, tn, formatDate, dir, weekdayOrder, weekdayShort } = useI18n();
  const { project } = useSession();
  const { data: requests, isLoading } = useTimeOff();
  const { data: people } = usePeople();
  const reviewer = can.reviewTimeOff(project);

  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [personId, setPersonId] = useState<number | null>(null);
  const today = new Date();
  const [cursor, setCursor] = useState({ year: today.getFullYear(), month: today.getMonth() });

  const submit = useConfigMutation(
    (payload: unknown) => api.post<TimeOff>("/api/time-off", payload),
    [keys.timeOff],
  );
  const review = useConfigMutation(
    ({ id, action }: { id: number; action: "approve" | "deny" | "cancel" }) =>
      api.post<TimeOff>(`/api/time-off/${id}/${action}`, {}),
    [keys.timeOff],
  );

  const personName = (id: number) =>
    people?.find((person) => person.id === id)?.full_name ?? `#${id}`;
  const range = (request: TimeOff) =>
    `${formatDate(request.start_date)} ${dir === "rtl" ? "←" : "→"} ${formatDate(request.end_date)}`;

  function send(event: React.FormEvent) {
    event.preventDefault();
    if (!start || !end) return;
    submit.mutate({
      // A reviewer may record an absence for anyone; everyone else may only
      // request their own, and the server refuses anything else regardless.
      person_id: reviewer ? personId : undefined,
      start_date: start,
      end_date: end,
      reason: reason || undefined,
    });
    setReason("");
  }

  const pending = requests?.filter((request) => request.status === "PENDING") ?? [];
  const settled = requests?.filter((request) => request.status !== "PENDING") ?? [];
  const away = awayByDay(requests ?? []);
  const grid = monthGrid(cursor.year, cursor.month, weekdayOrder);
  const monthLabel = formatDate(`${cursor.year}-${String(cursor.month + 1).padStart(2, "0")}-01`, {
    month: "long",
    year: "numeric",
  });
  const step = (delta: number) =>
    setCursor(({ year, month }) => {
      const d = new Date(year, month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  const shade = (n: number) =>
    n >= 3
      ? "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200"
      : n === 2
        ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        : n === 1
          ? "bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-200"
          : "";

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("timeoff.title")}</h1>
        <p className="text-sm text-slate-500">{t("timeoff.subtitle")}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <div className="space-y-4">
          <section className="card space-y-3 bg-indigo-50/60 dark:bg-slate-800">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-base font-semibold">{monthLabel}</div>
                <div className="text-xs text-slate-500">{t("timeoff.density")}</div>
              </div>
              <div className="flex gap-1">
                <button className="btn-ghost p-1.5" onClick={() => step(-1)} aria-label={t("timeoff.prevMonth")}>
                  <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />
                </button>
                <button className="btn-ghost p-1.5" onClick={() => step(1)} aria-label={t("timeoff.nextMonth")}>
                  <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
                </button>
              </div>
            </div>
            <table className="w-full text-center text-sm" aria-label={monthLabel}>
              <thead>
                <tr>
                  {weekdayOrder.map((d) => (
                    <th key={d} className="pb-1 text-[11px] font-semibold text-slate-500">
                      {weekdayShort(d)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grid.map((week, i) => (
                  <tr key={i}>
                    {week.map((day) => {
                      const n = away.get(day.iso) ?? 0;
                      return (
                        <td key={day.iso} className="p-0.5">
                          <div
                            title={n ? tn("timeoff.away", n) : undefined}
                            className={`mx-auto flex h-9 w-9 items-center justify-center rounded-lg tabular-nums ${
                              day.inMonth ? shade(n) : "text-slate-300 dark:text-slate-600"
                            } ${n > 0 && day.inMonth ? "font-semibold" : ""}`}
                          >
                            {day.day}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-indigo-200 dark:bg-indigo-800" aria-hidden />1</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-amber-200 dark:bg-amber-800" aria-hidden />2</span>
              <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded bg-red-200 dark:bg-red-800" aria-hidden />3+</span>
            </div>
          </section>

          <section className="card">
            <h2 className="label">{reviewer ? t("timeoff.record") : t("timeoff.request")}</h2>
            <form onSubmit={send} className="space-y-3">
              {reviewer && (
                <div>
                  <label className="label" htmlFor="timeoff-person">{t("table.person")}</label>
                  <select
                    id="timeoff-person"
                    className="input"
                    value={personId ?? ""}
                    onChange={(event) => setPersonId(event.target.value ? Number(event.target.value) : null)}
                  >
                    <option value="">{t("timeoff.myself")}</option>
                    {people?.map((person) => (
                      <option key={person.id} value={person.id}>{person.full_name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label" htmlFor="timeoff-start">{t("dashboard.from")}</label>
                  <input id="timeoff-start" className="input" type="date" value={start} required onChange={(event) => setStart(event.target.value)} />
                </div>
                <div>
                  <label className="label" htmlFor="timeoff-end">{t("dashboard.to")}</label>
                  <input id="timeoff-end" className="input" type="date" value={end} required onChange={(event) => setEnd(event.target.value)} />
                </div>
              </div>
              <div>
                <label className="label" htmlFor="timeoff-reason">{t("timeoff.reason")}</label>
                <input id="timeoff-reason" className="input" value={reason} onChange={(event) => setReason(event.target.value)} />
              </div>
              <button className="btn-primary w-full justify-center" type="submit" disabled={submit.isPending}>
                <Plus className="h-4 w-4" aria-hidden />
                {reviewer ? t("timeoff.recordButton") : t("timeoff.requestButton")}
              </button>
            </form>
            <div className="mt-2">
              <MutationError error={submit.error ?? review.error} />
            </div>
            {!reviewer && <p className="mt-2 text-xs text-slate-500">{t("timeoff.onlyApproved")}</p>}
          </section>
        </div>

        <section className="card min-w-0 space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-base font-semibold">{reviewer ? t("timeoff.all") : t("timeoff.mine")}</h2>
            {reviewer && (
              <span className="text-xs text-slate-500">{t("timeoff.awaiting", { count: pending.length })}</span>
            )}
          </div>
          {isLoading ? (
            <Spinner />
          ) : !requests?.length ? (
            <EmptyState
              title={t("timeoff.emptyTitle")}
              hint={project?.person_id === null && !reviewer ? t("error.notLinked") : undefined}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    {reviewer && <th className="th">{t("table.person")}</th>}
                    <th className="th">{t("timeoff.dates")}</th>
                    <th className="th">{t("timeoff.duration")}</th>
                    <th className="th">{t("timeoff.reasonCol")}</th>
                    <th className="th">{t("timeoff.statusCol")}</th>
                    <th className="th text-end">{t("edit.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...pending, ...settled].map((request) => (
                    <tr key={request.id} className="border-b border-slate-100 last:border-0 dark:border-slate-700/60">
                      {reviewer && (
                        <td className="td">
                          <span className="flex items-center gap-2">
                            <Avatar name={personName(request.person_id)} id={request.person_id} size="sm" />
                            <span className="font-medium">{personName(request.person_id)}</span>
                          </span>
                        </td>
                      )}
                      <td className="td whitespace-nowrap tabular-nums">{range(request)}</td>
                      <td className="td tabular-nums">{tn("timeoff.days", daysInRequest(request))}</td>
                      <td className="td text-slate-500">{request.reason ?? "—"}</td>
                      <td className="td">
                        <span className={`badge px-2 py-1 ${STATUS_TONES[request.status]}`}>
                          {t(`timeoffStatus.${request.status}`)}
                        </span>
                      </td>
                      <td className="td">
                        <div className="flex justify-end gap-1">
                          {reviewer && request.status === "PENDING" && (
                            <>
                              <button
                                className="btn rounded-lg bg-emerald-50 p-1.5 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950 dark:text-emerald-300"
                                onClick={() => review.mutate({ id: request.id, action: "approve" })}
                                aria-label={t("timeoff.approve")}
                                title={t("timeoff.approve")}
                              >
                                <Check className="h-4 w-4" aria-hidden />
                              </button>
                              <button
                                className="btn rounded-lg bg-red-50 p-1.5 text-red-700 hover:bg-red-100 dark:bg-red-950 dark:text-red-300"
                                onClick={() => review.mutate({ id: request.id, action: "deny" })}
                                aria-label={t("timeoff.deny")}
                                title={t("timeoff.deny")}
                              >
                                <X className="h-4 w-4" aria-hidden />
                              </button>
                            </>
                          )}
                          {(request.status === "PENDING" || request.status === "APPROVED") && (
                            <button
                              className="btn-ghost px-2 py-1 text-xs"
                              onClick={() => review.mutate({ id: request.id, action: "cancel" })}
                            >
                              {t("common.cancel")}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {reviewer && <p className="text-xs text-slate-500">{t("timeoff.approveHint")}</p>}
        </section>
      </div>
    </div>
  );
}
