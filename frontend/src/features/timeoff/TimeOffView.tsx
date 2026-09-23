import { useState } from "react";
import { Check, Plus, X } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, usePeople, useTimeOff } from "@/api/queries";
import { can, useSession } from "@/hooks/useSession";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import { MutationError } from "@/features/setup/steps/parts";
import type { TimeOff, TimeOffStatus } from "@/types/api";

const STATUS_TONES: Record<TimeOffStatus, string> = {
  PENDING: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  APPROVED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  DENIED: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
  CANCELLED: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

export function TimeOffView() {
  const { t, formatDate, dir } = useI18n();
  const { user } = useSession();
  const { data: requests, isLoading } = useTimeOff();
  const { data: people } = usePeople();
  const reviewer = can.reviewTimeOff(user);

  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [personId, setPersonId] = useState<number | null>(null);

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

  return (
    <div className="space-y-4">
      <section className="card">
        <h2 className="label">{reviewer ? t("timeoff.record") : t("timeoff.request")}</h2>
        <form onSubmit={send} className="flex flex-wrap items-end gap-2">
          {reviewer && (
            <div>
              <label className="label" htmlFor="timeoff-person">{t("table.person")}</label>
              <select
                id="timeoff-person"
                className="input w-48"
                value={personId ?? ""}
                onChange={(event) =>
                  setPersonId(event.target.value ? Number(event.target.value) : null)
                }
              >
                <option value="">{t("timeoff.myself")}</option>
                {people?.map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="label" htmlFor="timeoff-start">{t("dashboard.from")}</label>
            <input
              id="timeoff-start"
              className="input w-40"
              type="date"
              value={start}
              required
              onChange={(event) => setStart(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="timeoff-end">{t("dashboard.to")}</label>
            <input
              id="timeoff-end"
              className="input w-40"
              type="date"
              value={end}
              required
              onChange={(event) => setEnd(event.target.value)}
            />
          </div>
          <div className="min-w-40 flex-1">
            <label className="label" htmlFor="timeoff-reason">{t("timeoff.reason")}</label>
            <input
              id="timeoff-reason"
              className="input"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
          <button className="btn-primary" type="submit" disabled={submit.isPending}>
            <Plus className="h-4 w-4" aria-hidden />
            {reviewer ? t("timeoff.recordButton") : t("timeoff.requestButton")}
          </button>
        </form>
        <div className="mt-2">
          <MutationError error={submit.error ?? review.error} />
        </div>
        {!reviewer && <p className="mt-2 text-xs text-slate-500">{t("timeoff.onlyApproved")}</p>}
      </section>

      {isLoading ? (
        <Spinner />
      ) : (
        <>
          {reviewer && (
            <section className="card">
              <h2 className="label">{t("timeoff.awaiting", { count: pending.length })}</h2>
              {pending.length === 0 ? (
                <p className="text-sm text-slate-500">{t("timeoff.nothingWaiting")}</p>
              ) : (
                <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                  {pending.map((request) => (
                    <li key={request.id} className="flex flex-wrap items-center gap-3 py-2">
                      <span className="text-sm font-medium">
                        {personName(request.person_id)}
                      </span>
                      <span className="text-sm tabular-nums text-slate-500">{range(request)}</span>
                      {request.reason && (
                        <span className="text-xs text-slate-500">{request.reason}</span>
                      )}
                      <div className="ms-auto flex gap-1">
                        <button
                          className="btn-ghost text-xs"
                          onClick={() =>
                            review.mutate({ id: request.id, action: "approve" })
                          }
                        >
                          <Check className="h-3.5 w-3.5" aria-hidden />
                          {t("timeoff.approve")}
                        </button>
                        <button
                          className="btn-ghost text-xs"
                          onClick={() => review.mutate({ id: request.id, action: "deny" })}
                        >
                          <X className="h-3.5 w-3.5" aria-hidden />
                          {t("timeoff.deny")}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs text-slate-500">{t("timeoff.approveHint")}</p>
            </section>
          )}

          <section className="card">
            <h2 className="label">{reviewer ? t("timeoff.all") : t("timeoff.mine")}</h2>
            {!requests?.length ? (
              <EmptyState
                title={t("timeoff.emptyTitle")}
                hint={
                  user?.person_id === null && !reviewer ? t("error.notLinked") : undefined
                }
              />
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {[...pending, ...settled].map((request) => (
                  <li key={request.id} className="flex flex-wrap items-center gap-3 py-2">
                    <span className={`badge ${STATUS_TONES[request.status]}`}>
                      {t(`timeoffStatus.${request.status}`)}
                    </span>
                    {reviewer && (
                      <span className="text-sm">{personName(request.person_id)}</span>
                    )}
                    <span className="text-sm tabular-nums text-slate-500">{range(request)}</span>
                    {request.reason && (
                      <span className="text-xs text-slate-500">{request.reason}</span>
                    )}
                    {(request.status === "PENDING" || request.status === "APPROVED") && (
                      <button
                        className="btn-ghost ms-auto text-xs"
                        onClick={() => review.mutate({ id: request.id, action: "cancel" })}
                      >
                        {t("common.cancel")}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
