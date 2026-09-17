import { useState } from "react";
import { FeasibilityPanel } from "@/features/setup/FeasibilityPanel";
import { DivisionsStep } from "@/features/setup/steps/DivisionsStep";
import { JobsStep } from "@/features/setup/steps/JobsStep";
import { LadderStep } from "@/features/setup/steps/LadderStep";
import { PeopleStep } from "@/features/setup/steps/PeopleStep";
import { RulesStep } from "@/features/setup/steps/RulesStep";
import { ShiftTemplatesStep } from "@/features/setup/steps/ShiftTemplatesStep";
import { SkillsStep } from "@/features/setup/steps/SkillsStep";

/**
 * Ongoing configuration.
 *
 * These are the same editors the wizard walks through, reused rather than
 * reimplemented: the wizard is only a guided order through them, so there is
 * one place where each kind of configuration is edited.
 */
const SECTIONS = [
  { id: "divisions", label: "Divisions", Component: DivisionsStep },
  { id: "ladder", label: "Proficiency", Component: LadderStep },
  { id: "skills", label: "Skills", Component: SkillsStep },
  { id: "templates", label: "Shift windows", Component: ShiftTemplatesStep },
  { id: "jobs", label: "Jobs", Component: JobsStep },
  { id: "people", label: "People", Component: PeopleStep },
  { id: "rules", label: "Rules", Component: RulesStep },
] as const;

export function ConfigView() {
  const [active, setActive] = useState<(typeof SECTIONS)[number]["id"]>("divisions");
  const section = SECTIONS.find((entry) => entry.id === active)!;

  return (
    <div className="grid gap-4 lg:grid-cols-[12rem_1fr]">
      <nav className="flex flex-wrap gap-1 lg:flex-col" aria-label="Configuration sections">
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
            {entry.label}
          </button>
        ))}
      </nav>

      <div className="space-y-4">
        <div className="card">
          <section.Component />
        </div>
        {/* Any structural change alters what can be staffed, so the verdict
            sits alongside the editors rather than only in the wizard. */}
        <div className="card">
          <h2 className="label">Can this be staffed?</h2>
          <FeasibilityPanel />
        </div>
      </div>
    </div>
  );
}
