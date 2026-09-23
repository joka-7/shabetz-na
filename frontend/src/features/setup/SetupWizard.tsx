import { useState } from "react";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { useSettings } from "@/api/queries";
import { FeasibilityPanel } from "./FeasibilityPanel";
import { DivisionsStep } from "./steps/DivisionsStep";
import { LadderStep } from "./steps/LadderStep";
import { SkillsStep } from "./steps/SkillsStep";
import { ShiftTemplatesStep } from "./steps/ShiftTemplatesStep";
import { JobsStep } from "./steps/JobsStep";
import { PeopleStep } from "./steps/PeopleStep";
import { RulesStep } from "./steps/RulesStep";
import { Spinner } from "@/components/ui";

/**
 * Guided first-run configuration.
 *
 * Every step writes through the normal configuration endpoints, so nothing
 * here is special-cased: the wizard is a friendlier path through the same
 * screens an administrator uses later to change any of it.
 */
const STEPS = [
  { id: "divisions", label: "Divisions", Component: DivisionsStep },
  { id: "ladder", label: "Proficiency", Component: LadderStep },
  { id: "skills", label: "Skills", Component: SkillsStep },
  { id: "templates", label: "Shift windows", Component: ShiftTemplatesStep },
  { id: "jobs", label: "Jobs", Component: JobsStep },
  { id: "people", label: "People", Component: PeopleStep },
  { id: "rules", label: "Rules", Component: RulesStep },
  { id: "review", label: "Review", Component: null },
] as const;

export function SetupWizard({ onFinished }: { onFinished: () => void | Promise<void> }) {
  const [index, setIndex] = useState(0);
  const { isLoading } = useSettings();

  if (isLoading) {
    return (
      <div className="p-8">
        <Spinner label="Loading configuration…" />
      </div>
    );
  }

  const step = STEPS[index]!;
  const isReview = step.id === "review";

  return (
    <div className="mx-auto max-w-5xl p-4">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Set up your organization</h1>
        <p className="mt-1 text-sm text-slate-500">
          Nothing is preset. Divisions, shift windows, skills and staffing rules are
          whatever you define here, and every one of them stays editable afterwards.
        </p>
      </header>

      {/* Steps are addressable rather than strictly linear: each one saves on
          its own, so revisiting an earlier step never discards later work. */}
      <ol className="mb-6 flex flex-wrap gap-1" aria-label="Setup steps">
        {STEPS.map((entry, position) => {
          const state =
            position === index ? "current" : position < index ? "done" : "upcoming";
          return (
            <li key={entry.id}>
              <button
                onClick={() => setIndex(position)}
                aria-current={state === "current" ? "step" : undefined}
                className={`btn text-xs ${
                  state === "current"
                    ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                    : state === "done"
                      ? "text-emerald-700 hover:bg-slate-100 dark:text-emerald-400 dark:hover:bg-slate-800"
                      : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}
              >
                {state === "done" && <Check className="h-3 w-3" aria-hidden />}
                {position + 1}. {entry.label}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="card">
        {isReview ? (
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-medium">Review</h2>
              <p className="mt-1 text-sm text-slate-500">
                Before generating anything, check that what you configured can actually
                be staffed.
              </p>
            </div>
            <FeasibilityPanel />
          </div>
        ) : (
          <step.Component />
        )}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <button
          className="btn-ghost"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back
        </button>

        {isReview ? (
          <button className="btn-primary" onClick={() => void onFinished()}>
            Finish setup
            <Check className="h-4 w-4" aria-hidden />
          </button>
        ) : (
          <button
            className="btn-primary"
            onClick={() => setIndex((i) => Math.min(STEPS.length - 1, i + 1))}
          >
            Next
            <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}
