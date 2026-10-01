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
import { Logo } from "@/components/Logo";
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

  const stepCount = STEPS.length;

  return (
    <div className="mx-auto max-w-7xl p-4 pb-28">
      <header className="mb-6 flex flex-wrap items-start gap-3">
        <Logo className="h-10 w-10 shrink-0" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{t("wizard.title")}</h1>
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
        <p className="mb-4 rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-900 dark:bg-indigo-950 dark:text-indigo-200">
          {t("wizard.firstRunHint")}
        </p>
      )}

      {/* Steps are addressable rather than strictly linear: each one saves on
          its own, so revisiting an earlier step never discards later work. */}
      <ol className="card mb-6 flex items-center gap-1 overflow-x-auto" aria-label={t("wizard.steps")}>
        {STEPS.map((entry, position) => {
          const state = position === index ? "current" : position < index ? "done" : "upcoming";
          return (
            <li key={entry.id} className="flex flex-1 items-center gap-1">
              <button
                onClick={() => setIndex(position)}
                aria-current={state === "current" ? "step" : undefined}
                className={`flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-start text-xs ${
                  state === "current" ? "bg-indigo-50 dark:bg-indigo-950" : "hover:bg-slate-100 dark:hover:bg-slate-700"
                }`}
              >
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    state === "done"
                      ? "bg-emerald-600 text-white"
                      : state === "current"
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-500 dark:bg-slate-700"
                  }`}
                >
                  {state === "done" ? <Check className="h-4 w-4" aria-hidden /> : position + 1}
                </span>
                <span
                  className={`hidden truncate font-semibold md:block ${
                    state === "upcoming" ? "text-slate-500" : ""
                  }`}
                >
                  {t(entry.label)}
                </span>
              </button>
              {position < stepCount - 1 && (
                <span
                  className={`h-0.5 min-w-3 flex-1 rounded ${
                    position < index ? "bg-emerald-500" : "bg-slate-200 dark:bg-slate-700"
                  }`}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>

      <div className={isReview ? "" : "grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]"}>
        <div className="card min-w-0">
          {isReview ? (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold">{t("section.review")}</h2>
                <p className="mt-1 text-sm text-slate-500">{t("wizard.reviewIntro")}</p>
              </div>
              <FeasibilityPanel />
            </div>
          ) : (
            step.Component && <step.Component />
          )}
        </div>
        {!isReview && (
          <aside className="card hidden h-fit space-y-3 xl:block xl:sticky xl:top-4">
            <h2 className="text-base font-semibold">{t("feasibility.heading")}</h2>
            <FeasibilityPanel compact />
          </aside>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 backdrop-blur dark:border-slate-700 dark:bg-slate-800/95">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 p-3">
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

          <span className="hidden text-xs text-slate-500 sm:inline">{t("wizard.autosaved")}</span>

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
    </div>
  );
}
