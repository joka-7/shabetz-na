import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useDivisions, useSettings } from "@/api/queries";
import { Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { Settings } from "@/types/api";
import { MutationError, StepShell } from "./parts";

/** Every zone the browser knows, with the saved one kept even if it does not. */
function timeZones(current: string): string[] {
  const intl = Intl as { supportedValuesOf?: (key: string) => string[] };
  const known = intl.supportedValuesOf?.("timeZone") ?? [];
  return Array.from(new Set(["UTC", current, ...known]));
}

export function RulesStep() {
  const { t, tn } = useI18n();
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
    <StepShell title={t("rules.title")} intro={t("rules.intro")}>
      <div className="space-y-4">
        <div>
          <label className="label" htmlFor="rest">
            {t("rules.rest", { hours: draft.rest_period_hours })}
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
          <p className="mt-1 text-xs text-slate-500">{t("rules.restHint")}</p>
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
            {t("rules.rotate")}
          </label>
          <p className="mt-1 text-xs text-slate-500">{t("rules.rotateHint")}</p>
        </div>

        {draft.rotation_enabled && (
          <>
            <div>
              <label className="label" htmlFor="block-days">
                {t("rules.blockDays")}
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
                  {tn("rules.cycle", divisions?.length ?? 0, { days: cycleDays })}
                </p>
              )}
            </div>

            <div>
              <label className="label" htmlFor="anchor">
                {t("rules.anchor")}
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
              <p className="mt-1 text-xs text-slate-500">{t("rules.anchorHint")}</p>
            </div>
          </>
        )}

        <div>
          <label className="label" htmlFor="org-name">{t("rules.orgName")}</label>
          <input
            id="org-name"
            className="input"
            value={draft.organization_name}
            onChange={(event) => setDraft({ ...draft, organization_name: event.target.value })}
          />
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.fairness_carry_over}
              onChange={(event) =>
                setDraft({ ...draft, fairness_carry_over: event.target.checked })
              }
            />
            {t("rules.carryOver")}
          </label>
          <p className="mt-1 text-xs text-slate-500">{t("rules.carryOverHint")}</p>
        </div>

        <div>
          <label className="label" htmlFor="timezone">{t("rules.timezone")}</label>
          <select
            id="timezone"
            className="input"
            value={draft.timezone}
            onChange={(event) => setDraft({ ...draft, timezone: event.target.value })}
          >
            {timeZones(draft.timezone).map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">{t("rules.timezoneHint")}</p>
        </div>

        <MutationError error={save.error} />

        <button
          className="btn-primary"
          onClick={() => save.mutate(draft)}
          disabled={save.isPending}
        >
          <Save className="h-4 w-4" aria-hidden />
          {save.isPending ? t("common.saving") : save.isSuccess ? t("common.saved") : t("rules.save")}
        </button>
      </div>
    </StepShell>
  );
}
