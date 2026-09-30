import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { requestSwap, swapKeys, useColleagues } from "@/api/queries";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import { shiftWindow } from "@/lib/schedule";
import type { Assignment } from "@/types/api";

/** Offer one of your published shifts to a colleague. */
export function SwapDialog({
  shift,
  onClose,
  onSent,
}: {
  shift: Assignment;
  onClose: () => void;
  onSent: () => void;
}) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const colleagues = useColleagues(true);
  const [to, setTo] = useState<number | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const send = useMutation({
    mutationFn: () =>
      requestSwap({
        job_id: shift.job_id,
        template_id: shift.template_id,
        calendar_date: shift.calendar_date,
        to_person_id: to!,
        note: note.trim() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: swapKeys.all });
      onSent();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="swap-title" className="card w-full max-w-md space-y-4">
        <div className="flex items-start justify-between gap-2">
          <h2 id="swap-title" className="text-base font-semibold">{t("swap.dialogTitle")}</h2>
          <button className="btn-ghost p-1" onClick={onClose} aria-label={t("common.close")}>
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <p className="text-sm">
          {formatDate(shift.calendar_date, { weekday: "long", day: "numeric", month: "short" })} ·{" "}
          <span dir="ltr" className="tabular-nums">{shiftWindow(shift)}</span> · {shift.job_name}
        </p>
        <div>
          <label className="label" htmlFor="swap-to">{t("swap.giveTo")}</label>
          <select
            id="swap-to"
            className="input"
            value={to ?? ""}
            onChange={(event) => setTo(event.target.value ? Number(event.target.value) : null)}
          >
            <option value="">{t("edit.choose")}</option>
            {(colleagues.data ?? []).map((c) => (
              <option key={c.person_id} value={c.person_id}>{c.name}</option>
            ))}
          </select>
          {colleagues.data?.length === 0 && (
            <p className="mt-1 text-xs text-slate-500">{t("swap.noColleagues")}</p>
          )}
        </div>
        <div>
          <label className="label" htmlFor="swap-note">{t("swap.note")}</label>
          <input
            id="swap-note"
            className="input"
            maxLength={500}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </div>
        {send.error ? <ErrorNotice message={errorText(send.error, t)} /> : null}
        <div className="flex gap-2">
          <button className="btn-primary" disabled={to === null || send.isPending} onClick={() => send.mutate()}>
            {t("swap.send")}
          </button>
          <button className="btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
        </div>
      </div>
    </div>
  );
}
