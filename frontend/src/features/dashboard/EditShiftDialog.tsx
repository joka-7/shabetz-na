import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import {
  addShiftPerson,
  checkAssignment,
  fetchSuggestions,
  reassignShift,
  removeShiftPerson,
  useDivisions,
  useJobs,
  usePeople,
  useTemplates,
} from "@/api/queries";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import { shiftWindow } from "@/lib/schedule";
import type { Assignment, ScheduleRun } from "@/types/api";
import { conflictText } from "./conflictText";

export type EditTarget =
  | { kind: "reassign"; assignment: Assignment }
  /** `slot` pre-fills the shift, e.g. when fixing a gap from the warnings list. */
  | { kind: "add"; slot?: { job_id: number; template_id: number; calendar_date: string } };

/**
 * Change who works a shift after the schedule was generated.
 *
 * The server checks every proposed change and reports the rules it would
 * break. They are shown here as the person is picked, and saving a change
 * that breaks one needs an explicit acknowledgement -- an override is allowed,
 * a silent one is not.
 */
export function EditShiftDialog({
  run,
  target,
  onClose,
  onSaved,
}: {
  run: ScheduleRun;
  target: EditTarget;
  onClose: () => void;
  onSaved: (run: ScheduleRun) => void;
}) {
  const { t, formatDate } = useI18n();
  const { data: people = [] } = usePeople();
  const { data: divisions = [] } = useDivisions();
  const { data: jobs = [] } = useJobs();
  const { data: templates = [] } = useTemplates();

  const current = target.kind === "reassign" ? target.assignment : null;
  const preset = current ?? (target.kind === "add" ? target.slot : undefined);
  const [jobId, setJobId] = useState<number | null>(preset?.job_id ?? null);
  const [templateId, setTemplateId] = useState<number | null>(preset?.template_id ?? null);
  const [date, setDate] = useState<string>(preset?.calendar_date ?? "");
  const [personId, setPersonId] = useState<number | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const divisionName = useMemo(
    () => new Map(divisions.map((division) => [division.id, division.name])),
    [divisions],
  );
  const job = jobs.find((candidate) => candidate.id === jobId);
  const windowOptions = useMemo(
    () => templates.filter((template) => job?.shift_template_ids.includes(template.id)),
    [templates, job],
  );
  const template = templates.find((candidate) => candidate.id === templateId);

  const slot =
    jobId !== null && templateId !== null && date
      ? { job_id: jobId, template_id: templateId, calendar_date: date }
      : null;

  const candidates = useMemo(
    () =>
      people
        .filter((person) => person.is_active && person.id !== current?.person_id)
        .sort((a, b) => a.full_name.localeCompare(b.full_name)),
    [people, current],
  );
  const person = people.find((candidate) => candidate.id === personId);

  const suggestions = useQuery({
    queryKey: ["assignment-suggestions", run.schedule_id, slot, current?.person_id ?? null],
    enabled: slot !== null,
    queryFn: () => fetchSuggestions(run.schedule_id, slot!, current?.person_id ?? null),
  });
  const clean = (suggestions.data ?? []).filter((s) => s.conflicts.length === 0).slice(0, 5);

  const check = useQuery({
    queryKey: ["assignment-check", run.schedule_id, slot, personId, current?.person_id ?? null],
    enabled: slot !== null && personId !== null,
    queryFn: () =>
      checkAssignment(run.schedule_id, {
        ...slot!,
        person_id: personId!,
        replaces_person_id: current?.person_id ?? null,
      }),
  });
  const conflicts = check.data?.conflicts ?? [];

  const save = useMutation({
    mutationFn: () =>
      current
        ? reassignShift(run.schedule_id, {
            ...slot!,
            from_person_id: current.person_id,
            to_person_id: personId!,
            acknowledge_conflicts: acknowledged,
          })
        : addShiftPerson(run.schedule_id, {
            ...slot!,
            person_id: personId!,
            acknowledge_conflicts: acknowledged,
          }),
    onSuccess: onSaved,
  });

  const remove = useMutation({
    mutationFn: () =>
      removeShiftPerson(
        run.schedule_id,
        {
          job_id: current!.job_id,
          template_id: current!.template_id,
          calendar_date: current!.calendar_date,
        },
        current!.person_id,
      ),
    onSuccess: onSaved,
  });

  const conflictParams = {
    person: person?.full_name ?? "",
    job: job?.name ?? "",
    window: template?.name ?? "",
    date: date ? formatDate(date) : "",
  };
  const canSave =
    slot !== null &&
    personId !== null &&
    !check.isFetching &&
    (conflicts.length === 0 || acknowledged) &&
    !save.isPending;
  const error = save.error ?? remove.error;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-shift-title"
        className="card max-h-full w-full max-w-lg space-y-4 overflow-auto"
      >
        <div className="flex items-start justify-between gap-2">
          <h2 id="edit-shift-title" className="text-base font-semibold">
            {current ? t("edit.titleReassign") : t("edit.titleAdd")}
          </h2>
          <button className="btn-ghost p-1" onClick={onClose} aria-label={t("common.close")}>
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        {current ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-slate-500">{t("table.job")}</dt>
            <dd>{current.job_name}</dd>
            <dt className="text-slate-500">{t("table.date")}</dt>
            <dd>{formatDate(current.calendar_date, { weekday: "short", day: "numeric", month: "short" })}</dd>
            <dt className="text-slate-500">{t("table.window")}</dt>
            <dd>
              {current.template_name}{" "}
              <span dir="ltr" className="tabular-nums text-slate-500">{shiftWindow(current)}</span>
            </dd>
            <dt className="text-slate-500">{t("edit.current")}</dt>
            <dd className="font-medium">{current.person_name}</dd>
          </dl>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="label" htmlFor="edit-job">{t("table.job")}</label>
              <select
                id="edit-job"
                className="input"
                value={jobId ?? ""}
                onChange={(event) => {
                  setJobId(event.target.value ? Number(event.target.value) : null);
                  setTemplateId(null);
                  setAcknowledged(false);
                }}
              >
                <option value="">{t("edit.choose")}</option>
                {jobs.filter((j) => j.is_active).map((j) => (
                  <option key={j.id} value={j.id}>{j.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="edit-window">{t("table.window")}</label>
              <select
                id="edit-window"
                className="input"
                value={templateId ?? ""}
                disabled={!job}
                onChange={(event) => {
                  setTemplateId(event.target.value ? Number(event.target.value) : null);
                  setAcknowledged(false);
                }}
              >
                <option value="">{t("edit.choose")}</option>
                {windowOptions.map((option) => (
                  <option key={option.id} value={option.id}>{option.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="edit-date">{t("table.date")}</label>
              <input
                id="edit-date"
                className="input"
                type="date"
                min={String(run.params.start_date ?? "")}
                max={String(run.params.end_date ?? "")}
                value={date}
                onChange={(event) => {
                  setDate(event.target.value);
                  setAcknowledged(false);
                }}
              />
            </div>
          </div>
        )}

        {slot !== null && !suggestions.isLoading && (
          <div>
            <div className="label">{t("edit.suggested")}</div>
            {clean.length === 0 ? (
              <p className="text-xs text-slate-500">{t("edit.noneFree")}</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {clean.map((candidate) => (
                  <button
                    key={candidate.person_id}
                    type="button"
                    className={`btn text-xs ${
                      personId === candidate.person_id
                        ? "bg-indigo-600 text-white dark:bg-indigo-500"
                        : "border border-slate-300 dark:border-slate-700"
                    }`}
                    onClick={() => {
                      setPersonId(candidate.person_id);
                      setAcknowledged(false);
                    }}
                  >
                    {candidate.person_name}
                    <span className="text-[10px] opacity-70">
                      {t("edit.shiftsHeld", { count: candidate.shifts_in_schedule })}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div>
          <label className="label" htmlFor="edit-person">{t("edit.assignTo")}</label>
          <select
            id="edit-person"
            className="input"
            value={personId ?? ""}
            onChange={(event) => {
              setPersonId(event.target.value ? Number(event.target.value) : null);
              setAcknowledged(false);
            }}
          >
            <option value="">{t("edit.choose")}</option>
            {candidates.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.full_name} — {divisionName.get(candidate.division_id) ?? ""}
              </option>
            ))}
          </select>
        </div>

        {personId !== null && slot !== null && (
          <div aria-live="polite">
            {check.isFetching ? (
              <p className="text-sm text-slate-500">{t("edit.checking")}</p>
            ) : conflicts.length === 0 ? (
              <p className="text-sm text-emerald-700 dark:text-emerald-400">{t("edit.noConflicts")}</p>
            ) : (
              <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950">
                <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
                  {t("edit.conflictsTitle")}
                </p>
                <ul className="list-disc ps-5 text-sm text-amber-900 dark:text-amber-200">
                  {conflicts.map((conflict) => (
                    <li key={conflict.kind}>
                      {conflictText(t, conflict.kind, conflictParams, conflict.message)}
                    </li>
                  ))}
                </ul>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(event) => setAcknowledged(event.target.checked)}
                  />
                  {t("edit.acknowledge")}
                </label>
              </div>
            )}
          </div>
        )}

        {error ? <ErrorNotice message={errorText(error, t)} /> : null}

        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-primary" disabled={!canSave} onClick={() => save.mutate()}>
            {save.isPending ? t("common.saving") : t("edit.save")}
          </button>
          <button className="btn-ghost" onClick={onClose}>{t("common.cancel")}</button>

          {current && (
            <div className="ms-auto flex items-center gap-2">
              {confirmingRemove ? (
                <>
                  <span className="text-sm">{t("edit.confirmRemove", { name: current.person_name })}</span>
                  <button
                    className="btn bg-rose-600 text-white hover:bg-rose-700"
                    disabled={remove.isPending}
                    onClick={() => remove.mutate()}
                  >
                    {t("edit.confirmRemoveYes")}
                  </button>
                </>
              ) : (
                <button
                  className="btn-ghost text-rose-700 dark:text-rose-400"
                  onClick={() => setConfirmingRemove(true)}
                >
                  {t("edit.remove")}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
