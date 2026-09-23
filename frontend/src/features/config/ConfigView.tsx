import { useState } from "react";
import { FeasibilityPanel } from "@/features/setup/FeasibilityPanel";
import { DivisionsStep } from "@/features/setup/steps/DivisionsStep";
import { JobsStep } from "@/features/setup/steps/JobsStep";
import { LadderStep } from "@/features/setup/steps/LadderStep";
import { PeopleStep } from "@/features/setup/steps/PeopleStep";
import { RulesStep } from "@/features/setup/steps/RulesStep";
import { ShiftTemplatesStep } from "@/features/setup/steps/ShiftTemplatesStep";
import { SkillsStep } from "@/features/setup/steps/SkillsStep";
import { useI18n } from "@/i18n";
import type { MessageKey } from "@/i18n";
import { UsersAdmin } from "./UsersAdmin";

/**
 * Ongoing configuration.
 *
 * These are the same editors the wizard walks through, reused rather than
 * reimplemented: the wizard is only a guided order through them, so there is
 * one place where each kind of configuration is edited.
 */
const SECTIONS: readonly { id: string; label: MessageKey; Component: () => JSX.Element }[] = [
  { id: "divisions", label: "section.divisions", Component: DivisionsStep },
  { id: "ladder", label: "section.ladder", Component: LadderStep },
  { id: "skills", label: "section.skills", Component: SkillsStep },
  { id: "templates", label: "section.templates", Component: ShiftTemplatesStep },
  { id: "jobs", label: "section.jobs", Component: JobsStep },
  { id: "people", label: "section.people", Component: PeopleStep },
  { id: "rules", label: "section.rules", Component: RulesStep },
  { id: "users", label: "section.users", Component: UsersAdmin },
];

export function ConfigView() {
  const { t } = useI18n();
  const [active, setActive] = useState("divisions");
  const section = SECTIONS.find((entry) => entry.id === active)!;

  return (
    <div className="grid gap-4 lg:grid-cols-[12rem_1fr]">
      <nav className="flex flex-wrap gap-1 lg:flex-col" aria-label={t("nav.configuration")}>
        {SECTIONS.map((entry) => (
          <button
            key={entry.id}
            onClick={() => setActive(entry.id)}
            aria-current={active === entry.id ? "page" : undefined}
            className={`btn justify-start text-sm ${
              active === entry.id
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                : "hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            {t(entry.label)}
          </button>
        ))}
      </nav>

      <div className="space-y-4">
        <div className="card">
          <section.Component />
        </div>
        {/* Any structural change alters what can be staffed, so the verdict
            sits alongside the editors rather than only in the wizard. Accounts
            are the exception: they change who may sign in, not staffing. */}
        {active !== "users" && (
          <div className="card">
            <h2 className="label">{t("feasibility.heading")}</h2>
            <FeasibilityPanel />
          </div>
        )}
      </div>
    </div>
  );
}
