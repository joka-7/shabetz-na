import { useState } from "react";
import { Moon, Pencil, Plus, Trash2, X } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useJobs, useTemplates } from "@/api/queries";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import {
  crossesMidnight,
  matchingTemplate,
  rangeOf,
  windowLabel,
  windowsOf,
  type HoursRange,
} from "@/lib/tasks";
import type { Job, ShiftTemplate } from "@/types/api";

interface Draft {
  id: number | null;
  name: string;
  people: number;
  hours: HoursRange[];
  notes: string;
}

const blank = (): Draft => ({ id: null, name: "", people: 1, hours: [{ from: "08:00", to: "16:00" }], notes: "" });

/**
 * Tasks, their hours and how many people each needs, in one place.
 *
 * Underneath, a task is a job and its hours are shift windows. Typing clock
 * times here reuses a window that already has those hours or makes one, so
 * nobody has to set windows up separately first.
 */
export function TasksView() {
  const { t, tn } = useI18n();
  const { data: jobs, isLoading } = useJobs();
  const { data: templates = [] } = useTemplates();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const save = useConfigMutation(
    async (d: Draft) => {
      const { windows } = windowsOf(d.hours);
      // Every set of hours becomes a window: an existing one with those hours, else a new one.
      const ids: number[] = [];
      const known = [...templates];
      for (const w of windows) {
        const found = matchingTemplate(known, w);
        if (found) {
          ids.push(found.id);
          continue;
        }
        const created = await api.post<ShiftTemplate>("/api/config/shift-templates", {
          name: windowLabel(w),
          ...w,
        });
        known.push(created);
        ids.push(created.id);
      }
      const existing = jobs?.find((j) => j.id === d.id);
      const payload = {
        name: d.name.trim(),
        required_people_per_shift: Math.max(1, Math.floor(d.people) || 1),
        notes: d.notes.trim() || null,
        division_policy: existing?.division_policy ?? "ACTIVE_DIVISION_PREFERRED",
        priority: existing?.priority ?? null,
        shift_template_ids: ids,
        // Skill requirements are managed under Configuration and kept as they are.
        requirements: (existing?.requirements ?? []).map((r) => ({
          skill_id: r.skill_id,
          min_level_id: r.min_level_id,
          required_count: r.required_count,
          is_leadership: r.is_leadership,
        })),
      };
      return d.id === null
        ? api.post<Job>("/api/config/jobs", payload)
        : api.put<Job>(`/api/config/jobs/${d.id}`, payload);
    },
    [keys.jobs, keys.templates],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/jobs/${id}`),
    [keys.jobs],
  );

  function edit(job: Job) {
    setProblem(null);
    setDraft({
      id: job.id,
      name: job.name,
      people: job.required_people_per_shift,
      hours: job.shift_template_ids
        .map((id) => templates.find((tpl) => tpl.id === id))
        .filter((tpl): tpl is ShiftTemplate => Boolean(tpl))
        .map((tpl) => rangeOf(tpl)),
      notes: job.notes ?? "",
    });
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    if (!draft.name.trim()) return setProblem(t("tasks.needName"));
    const { windows, invalid } = windowsOf(draft.hours);
    if (windows.length === 0 || invalid) return setProblem(t("tasks.needHours"));
    setProblem(null);
    save.mutate(draft, { onSuccess: () => setDraft(null) });
  }

  const update = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const hoursOf = (job: Job) =>
    job.shift_template_ids
      .map((id) => templates.find((tpl) => tpl.id === id))
      .filter((tpl): tpl is ShiftTemplate => Boolean(tpl));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("tasks.title")}</h1>
          <p className="text-sm text-slate-500">{t("tasks.subtitle")}</p>
        </div>
        {!draft && (
          <button className="btn-primary ms-auto" onClick={() => { setProblem(null); setDraft(blank()); }}>
            <Plus className="h-4 w-4" aria-hidden />
            {t("tasks.add")}
          </button>
        )}
      </div>

      {draft && (
        <form onSubmit={submit} className="card space-y-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
            <div>
              <label className="label" htmlFor="task-name">{t("tasks.name")}</label>
              <input
                id="task-name"
                className="input"
                value={draft.name}
                autoFocus
                onChange={(event) => update({ name: event.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="task-people">{t("tasks.people")}</label>
              <input
                id="task-people"
                className="input"
                type="number"
                min={1}
                value={draft.people}
                onChange={(event) => update({ people: Number(event.target.value) })}
              />
            </div>
          </div>

          <fieldset>
            <legend className="label">{t("tasks.hours")}</legend>
            <div className="space-y-2">
              {draft.hours.map((range, index) => (
                <div key={index} className="flex flex-wrap items-center gap-2">
                  <input
                    className="input w-32"
                    type="time"
                    aria-label={t("tasks.from")}
                    value={range.from}
                    onChange={(event) =>
                      update({ hours: draft.hours.map((r, i) => (i === index ? { ...r, from: event.target.value } : r)) })
                    }
                  />
                  <span className="text-slate-400">–</span>
                  <input
                    className="input w-32"
                    type="time"
                    aria-label={t("tasks.to")}
                    value={range.to}
                    onChange={(event) =>
                      update({ hours: draft.hours.map((r, i) => (i === index ? { ...r, to: event.target.value } : r)) })
                    }
                  />
                  {draft.hours.length > 1 && (
                    <button
                      type="button"
                      className="btn-ghost p-1.5"
                      aria-label={t("tasks.removeHours")}
                      onClick={() => update({ hours: draft.hours.filter((_, i) => i !== index) })}
                    >
                      <X className="h-4 w-4" aria-hidden />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button
              type="button"
              className="btn-ghost mt-2 text-sm"
              onClick={() => update({ hours: [...draft.hours, { from: "16:00", to: "00:00" }] })}
            >
              <Plus className="h-4 w-4" aria-hidden />
              {t("tasks.addHours")}
            </button>
          </fieldset>

          <div>
            <label className="label" htmlFor="task-notes">{t("tasks.notes")}</label>
            <textarea
              id="task-notes"
              className="input min-h-20"
              placeholder={t("tasks.notesPlaceholder")}
              maxLength={2000}
              value={draft.notes}
              onChange={(event) => update({ notes: event.target.value })}
            />
          </div>

          {draft.id !== null && <p className="text-xs text-slate-500">{t("tasks.skillsKept")}</p>}
          {problem && <ErrorNotice message={problem} />}
          {save.error ? <ErrorNotice message={errorText(save.error, t)} /> : null}

          <div className="flex gap-2">
            <button className="btn-primary" type="submit" disabled={save.isPending}>
              {t("tasks.save")}
            </button>
            <button className="btn-ghost" type="button" onClick={() => setDraft(null)}>
              {t("tasks.cancel")}
            </button>
          </div>
        </form>
      )}

      {remove.error ? <ErrorNotice message={errorText(remove.error, t)} /> : null}

      {isLoading ? (
        <Skeleton className="h-32" />
      ) : !jobs?.length ? (
        <EmptyState title={t("tasks.empty")} hint={t("tasks.emptyHint")} />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {[...jobs].sort((a, b) => a.name.localeCompare(b.name)).map((job) => (
            <li key={job.id} className="card space-y-2">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-base font-semibold">{job.name}</h2>
                  <span className="badge bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
                    {tn("tasks.peopleCount", job.required_people_per_shift)}
                  </span>
                </div>
                <button className="btn-ghost p-1.5" onClick={() => edit(job)} aria-label={t("tasks.edit", { name: job.name })}>
                  <Pencil className="h-4 w-4" aria-hidden />
                </button>
                <button
                  className="btn-ghost p-1.5"
                  aria-label={t("tasks.remove", { name: job.name })}
                  onClick={() => window.confirm(t("tasks.remove", { name: job.name })) && remove.mutate(job.id)}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {hoursOf(job).length === 0 ? (
                  <span className="text-xs text-slate-400">{t("tasks.noHours")}</span>
                ) : (
                  hoursOf(job).map((tpl) => (
                    <span key={tpl.id} className="badge gap-1 bg-slate-100 tabular-nums text-slate-800 dark:bg-slate-800 dark:text-slate-200">
                      {windowLabel(tpl)}
                      {crossesMidnight(tpl) && <Moon className="h-3 w-3" aria-label={t("tasks.crosses")} />}
                    </span>
                  ))
                )}
              </div>
              {job.notes && <p className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">{job.notes}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
