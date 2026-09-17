import { useState } from "react";
import { Plus, Scissors } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useTemplates } from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import { clockTime } from "@/lib/schedule";
import type { ShiftTemplate } from "@/types/api";
import { MutationError, Row, RowList, StepShell } from "./parts";

export function ShiftTemplatesStep() {
  const { data: templates, isLoading } = useTemplates();
  const [name, setName] = useState("");
  const [start, setStart] = useState("08:00");
  const [duration, setDuration] = useState(8);
  const [splitCount, setSplitCount] = useState(3);

  const create = useConfigMutation(
    (payload: { name: string; start_hour: number; duration_hours: number }) =>
      api.post<ShiftTemplate>("/api/config/shift-templates", payload),
    [keys.templates],
  );
  const split = useConfigMutation(
    (payload: { shifts: number }) =>
      api.post<ShiftTemplate[]>("/api/config/shift-templates/split-day", payload),
    [keys.templates],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/shift-templates/${id}`),
    [keys.templates, keys.jobs],
  );

  function add(event: React.FormEvent) {
    event.preventDefault();
    const [hours, minutes] = start.split(":").map(Number);
    if (!name.trim() || hours === undefined) return;
    create.mutate({
      name: name.trim(),
      start_hour: hours + (minutes ?? 0) / 60,
      duration_hours: duration,
    });
    setName("");
  }

  return (
    <StepShell
      title="Shift windows"
      intro="Define the working windows your jobs run. Any start time, any length, any number — they may also overlap or leave gaps."
    >
      <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
        <div className="label">Quick start</div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="label" htmlFor="split-count">
              Split a day into equal windows
            </label>
            <input
              id="split-count"
              className="input w-24"
              type="number"
              min={1}
              max={24}
              value={splitCount}
              onChange={(event) => setSplitCount(Number(event.target.value))}
            />
          </div>
          <button
            className="btn-ghost"
            onClick={() => split.mutate({ shifts: splitCount })}
            disabled={split.isPending}
          >
            <Scissors className="h-4 w-4" aria-hidden />
            Generate {splitCount} × {(24 / splitCount).toFixed(1)}h
          </button>
        </div>
      </div>

      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <div className="min-w-40 flex-1">
          <label className="label" htmlFor="template-name">Name</label>
          <input
            id="template-name"
            className="input"
            placeholder="e.g. Night watch"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="template-start">Starts</label>
          <input
            id="template-start"
            className="input w-32"
            type="time"
            step={900}
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="template-duration">Hours</label>
          <input
            id="template-duration"
            className="input w-24"
            type="number"
            min={0.5}
            max={24}
            step={0.5}
            value={duration}
            onChange={(event) => setDuration(Number(event.target.value))}
          />
        </div>
        <button className="btn-primary" type="submit" disabled={create.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          Add
        </button>
      </form>

      <MutationError error={create.error ?? split.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !templates?.length ? (
        <EmptyState
          title="No shift windows yet"
          hint="Generate equal windows above, or add one with its own start time and length."
        />
      ) : (
        <>
          <DayStrip templates={templates} />
          <RowList>
            {templates.map((template) => {
              const end = template.start_hour + template.duration_hours;
              return (
                <Row
                  key={template.id}
                  deleteLabel={`Remove ${template.name}`}
                  onDelete={() => remove.mutate(template.id)}
                >
                  <div className="flex items-center gap-3 text-sm">
                    <span className="font-medium">{template.name}</span>
                    <span className="tabular-nums text-slate-500">
                      {clockTime(template.start_hour)}–{clockTime(end)}
                    </span>
                    <span className="text-xs text-slate-400">
                      {template.duration_hours}h
                      {end > 24 && " · crosses midnight"}
                    </span>
                  </div>
                </Row>
              );
            })}
          </RowList>
        </>
      )}
    </StepShell>
  );
}

/**
 * A 24-hour strip of the configured windows.
 *
 * Overlaps and gaps are both expressible now that start times are arbitrary,
 * and neither is apparent from a list of numbers — seeing the bars laid against
 * the clock is the only quick way to tell whether coverage is what was meant.
 */
function DayStrip({ templates }: { templates: ShiftTemplate[] }) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <div className="label">A day at a glance</div>

      <div className="relative mb-1 h-4">
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

      <div className="space-y-1">
        {templates.map((template) => {
          const end = template.start_hour + template.duration_hours;
          // A window running past midnight is drawn as two bars so the part
          // landing on the next day is still visible on the same strip.
          const segments =
            end <= 24
              ? [[template.start_hour, end] as const]
              : ([[template.start_hour, 24], [0, end - 24]] as const);
          return (
            <div key={template.id} className="flex items-center gap-2">
              <span className="w-24 shrink-0 truncate text-xs text-slate-500">
                {template.name}
              </span>
              <div className="relative h-5 flex-1 rounded bg-slate-100 dark:bg-slate-800">
                {segments.map(([from, to], index) => (
                  <div
                    key={index}
                    className="absolute top-0 h-5 rounded bg-slate-500/80 dark:bg-slate-500/60"
                    style={{
                      left: `${(from / 24) * 100}%`,
                      width: `${((to - from) / 24) * 100}%`,
                    }}
                    title={`${clockTime(from)}–${clockTime(to)}`}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
