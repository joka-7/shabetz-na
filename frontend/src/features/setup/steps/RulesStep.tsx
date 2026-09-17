import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useDivisions, useSettings } from "@/api/queries";
import { Spinner } from "@/components/ui";
import type { Settings } from "@/types/api";
import { MutationError, StepShell } from "./parts";

export function RulesStep() {
  const { data: settings, isLoading } = useSettings();
  const { data: divisions } = useDivisions();
  const [draft, setDraft] = useState<Settings | null>(null);

  useEffect(() => {
    if (settings && !draft) setDraft(settings);
  }, [settings, draft]);

  const save = useConfigMutation(
    (payload: Settings) => api.put<Settings>("/api/config/settings", payload),
    [keys.settings],
  );

  if (isLoading || !draft) return <Spinner />;

  const cycleDays = (divisions?.length ?? 0) * draft.rotation_block_days;

  return (
    <StepShell
      title="Scheduling rules"
      intro="How much rest people need between shifts, and how duty moves between divisions."
    >
      <div className="space-y-4">
        <div>
          <label className="label" htmlFor="rest">
            Minimum rest between shifts — {draft.rest_period_hours} hours
          </label>
          <input
            id="rest"
            type="range"
            min={0}
            max={24}
            step={0.5}
            value={draft.rest_period_hours}
            onChange={(event) =>
              setDraft({ ...draft, rest_period_hours: Number(event.target.value) })
            }
            className="w-full"
          />
          {/* Rest is the only limit on how often someone works, so it is worth
              being explicit that shortening it permits more shifts per day. */}
          <p className="mt-1 text-xs text-slate-500">
            This is the only limit on how often a person can be scheduled — there is no
            separate cap on shifts per day. A shorter window allows more shifts in a day.
          </p>
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.rotation_enabled}
              onChange={(event) =>
                setDraft({ ...draft, rotation_enabled: event.target.checked })
              }
            />
            Rotate duty between divisions
          </label>
          <p className="mt-1 text-xs text-slate-500">
            When off, anyone qualified and rested may be assigned to any job.
          </p>
        </div>

        {draft.rotation_enabled && (
          <>
            <div>
              <label className="label" htmlFor="block-days">
                Days each division holds duty
              </label>
              <input
                id="block-days"
                className="input w-28"
                type="number"
                min={1}
                value={draft.rotation_block_days}
                onChange={(event) =>
                  setDraft({ ...draft, rotation_block_days: Number(event.target.value) })
                }
              />
              {cycleDays > 0 && (
                <p className="mt-1 text-xs text-slate-500">
                  With {divisions?.length} divisions that is a {cycleDays}-day cycle.
                </p>
              )}
            </div>

            <div>
              <label className="label" htmlFor="anchor">
                Rotation start date (optional)
              </label>
              <input
                id="anchor"
                className="input w-48"
                type="date"
                value={draft.rotation_anchor_date ?? ""}
                onChange={(event) =>
                  setDraft({ ...draft, rotation_anchor_date: event.target.value || null })
                }
              />
              {/* Without a fixed anchor the cycle is measured from whatever
                  window is generated, so who is on duty can shift unexpectedly. */}
              <p className="mt-1 text-xs text-slate-500">
                Pin this to keep the cycle stable. Left empty, it is measured from the
                first day of whichever period you generate.
              </p>
            </div>
          </>
        )}

        <div>
          <label className="label" htmlFor="org-name">Organization name</label>
          <input
            id="org-name"
            className="input"
            value={draft.organization_name}
            onChange={(event) => setDraft({ ...draft, organization_name: event.target.value })}
          />
        </div>

        <MutationError error={save.error} />

        <button
          className="btn-primary"
          onClick={() => save.mutate(draft)}
          disabled={save.isPending}
        >
          <Save className="h-4 w-4" aria-hidden />
          {save.isPending ? "Saving…" : save.isSuccess ? "Saved" : "Save rules"}
        </button>
      </div>
    </StepShell>
  );
}
