import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, X } from "lucide-react";
import { useSettings } from "@/api/queries";
import { useI18n } from "@/i18n";
import type { MessageKey } from "@/i18n";
import { FeasibilityPanel } from "./FeasibilityPanel";
import { DivisionsStep } from "./steps/DivisionsStep";
import { LadderStep } from "./steps/LadderStep";
import { SkillsStep } from "./steps/SkillsStep";
import { ShiftTemplatesStep } from "./steps/ShiftTemplatesStep";
import { JobsStep } from "./steps/JobsStep";
import { PeopleStep } from "./steps/PeopleStep";
import { RulesStep } from "./steps/RulesStep";
import { LanguageSwitch, Spinner } from "@/components/ui";

/**
 * Guided first-run configuration.
 *
 * Every step writes through the normal configuration endpoints, so nothing
 * here is special-cased: the wizard is a friendlier path through the same
 * screens an administrator uses later to change any of it.
 */
const STEPS: { id: string; label: MessageKey; Component: (() => JSX.Element) | null }[] = [
  { id: "divisions", label: "section.divisions", Component: DivisionsStep },
  { id: "ladder", label: "section.ladder", Component: LadderStep },
  { id: "skills", label: "section.skills", Component: SkillsStep },
  { id: "templates", label: "section.templates", Component: ShiftTemplatesStep },
  { id: "jobs", label: "section.jobs", Component: JobsStep },
  { id: "people", label: "section.people", Component: PeopleStep },
  { id: "rules", label: "section.rules", Component: RulesStep },
  { id: "review", label: "section.review", Component: null },
];

export function SetupWizard({
  onFinished,
  firstRun,
}: {
  onFinished: () => void | Promise<void>;
  firstRun: boolean;
}) {
  const { t } = useI18n();
  const [index, setIndex] = useState(0);
  const [closing, setClosing] = useState(false);
  const { isLoading } = useSettings();

  if (isLoading) {
    return (
      <div className="p-8">
        <Spinner label={t("wizard.loading")} />
      </div>
    );
  }

  const step = STEPS[index]!;
  const isReview = step.Component === null;

  // Each step saves as it goes, so leaving at any point loses nothing; the
  // header's Setup button brings the wizard back.
  async function close() {
    setClosing(true);
    try {
      await onFinished();
    } finally {
      setClosing(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-4">
      <header className="mb-6 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">{t("wizard.title")}</h1>
          <p className="mt-1 text-sm text-slate-500">{t("wizard.intro")}</p>
        </div>
        <div className="flex items-center gap-2">
          <LanguageSwitch />
          <button className="btn-ghost text-xs" onClick={() => void close()} disabled={closing}>
            <X className="h-3.5 w-3.5" aria-hidden />
            {t("wizard.saveAndClose")}
          </button>
        </div>
      </header>

      {firstRun && index === 0 && (
        <p className="mb-4 rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          {t("wizard.firstRunHint")}
        </p>
      )}

      {/* Steps are addressable rather than strictly linear: each one saves on
          its own, so revisiting an earlier step never discards later work. */}
      <ol className="mb-6 flex flex-wrap gap-1" aria-label={t("wizard.steps")}>
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
                {position + 1}. {t(entry.label)}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="card">
        {isReview ? (
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-medium">{t("section.review")}</h2>
              <p className="mt-1 text-sm text-slate-500">{t("wizard.reviewIntro")}</p>
            </div>
            <FeasibilityPanel />
          </div>
        ) : (
          step.Component && <step.Component />
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        {index === 0 ? (
          <button className="btn-ghost" onClick={() => void close()} disabled={closing}>
            <X className="h-4 w-4" aria-hidden />
            {t("wizard.closeSetup")}
          </button>
        ) : (
          <button className="btn-ghost" onClick={() => setIndex((i) => Math.max(0, i - 1))}>
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />
            {t("wizard.back")}
          </button>
        )}

        {isReview ? (
          <button className="btn-primary" onClick={() => void close()} disabled={closing}>
            {t("wizard.finish")}
            <Check className="h-4 w-4" aria-hidden />
          </button>
        ) : (
          <button
            className="btn-primary"
            onClick={() => setIndex((i) => Math.min(STEPS.length - 1, i + 1))}
          >
            {t("wizard.next")}
            <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}
