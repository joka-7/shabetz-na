import { useState } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { useI18n } from "@/i18n";
import { blockingWarnings, warningsBySeverity } from "@/lib/schedule";
import type { ScheduleWarning } from "@/types/api";
import { conflictText, isConflictKind } from "./conflictText";

/**
 * The warning in the interface language, from the names the server recorded.
 * Runs stored before those were recorded fall back to the server's English.
 */
function useWarningText() {
  const { t, formatDate } = useI18n();
  return (warning: ScheduleWarning): string => {
    const params = {
      job: warning.job_name ?? "",
      window: warning.template_name ?? "",
      date: warning.calendar_date ? formatDate(warning.calendar_date) : "",
      assigned: warning.assigned ?? 0,
      required: warning.required ?? 0,
    };
    if (warning.kind === "UNDERSTAFFED" && warning.job_name) {
      return t("warning.understaffed", params);
    }
    if (warning.kind === "MISSING_ROLE" && warning.job_name && warning.skill_name) {
      return t("warning.missingRole", { ...params, skill: warning.skill_name });
    }
    if (warning.kind === "DIVISION_FALLBACK" && warning.job_name && warning.person_name) {
      return t("warning.fallback", { ...params, person: warning.person_name });
    }
    if (isConflictKind(warning.kind) && warning.person_name) {
      return conflictText(
        t,
        warning.kind,
        { person: warning.person_name, job: params.job, window: params.window, date: params.date },
        warning.message,
      );
    }
    return warning.message;
  };
}

const FIXABLE = new Set(["UNDERSTAFFED", "MISSING_ROLE"]);

const TONE = {
  ERROR: {
    icon: XCircle,
    box: "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950",
    tag: "text-red-700 dark:text-red-300",
    bar: "bg-red-500",
  },
  WARNING: {
    icon: AlertTriangle,
    box: "border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950",
    tag: "text-amber-800 dark:text-amber-300",
    bar: "bg-amber-500",
  },
  INFO: {
    icon: Info,
    box: "border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950",
    tag: "text-blue-700 dark:text-blue-300",
    bar: "bg-blue-500",
  },
} as const;

/** What needs attention, most serious first, with a one-click way to fix a gap. */
export function WarningsPanel({
  warnings,
  onFix,
}: {
  warnings: ScheduleWarning[];
  /** Present only for roles that may change a schedule. */
  onFix?: (warning: ScheduleWarning) => void;
}) {
  const { t } = useI18n();
  const text = useWarningText();
  const [showInfo, setShowInfo] = useState(false);
  const counts = warningsBySeverity(warnings);
  const blocking = blockingWarnings(warnings);

  if (warnings.length === 0) {
    return (
      <section className="card flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
        {t("warnings.none")}
      </section>
    );
  }

  const shown = showInfo ? warnings : blocking;

  return (
    <section className="card space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-semibold">{t("warnings.title")}</h2>
        {blocking.length > 0 && (
          <span className="badge rounded-full bg-red-100 px-2 text-red-800 dark:bg-red-950 dark:text-red-300">
            {blocking.length}
          </span>
        )}
        {counts.INFO > 0 && (
          <button
            className="btn-ghost ms-auto px-2 py-1 text-xs"
            onClick={() => setShowInfo((value) => !value)}
          >
            {showInfo ? t("warnings.hideInfo") : t("warnings.showInfo", { count: counts.INFO })}
          </button>
        )}
      </div>

      {blocking.length === 0 && !showInfo && (
        <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
          {t("warnings.onlyInfo", { count: counts.INFO })}
        </p>
      )}

      <ul className="max-h-[28rem] space-y-2 overflow-auto">
        {shown.map((warning, index) => {
          const tone = TONE[warning.severity];
          const Icon = tone.icon;
          return (
            <li
              key={`${warning.kind}-${warning.calendar_date}-${index}`}
              className={`relative overflow-hidden rounded-lg border p-3 ps-4 text-sm ${tone.box}`}
            >
              <span className={`absolute inset-y-0 start-0 w-1 ${tone.bar}`} aria-hidden />
              <div className={`mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide ${tone.tag}`}>
                <Icon className="h-3.5 w-3.5" aria-hidden />
                {t(`severity.${warning.severity}`)}
                {warning.required !== null && warning.assigned !== null && (
                  <span className="ms-auto tabular-nums">
                    {warning.assigned}/{warning.required}
                  </span>
                )}
              </div>
              <p>{text(warning)}</p>
              {onFix &&
                FIXABLE.has(warning.kind) &&
                warning.job_id !== null &&
                warning.template_id !== null &&
                warning.calendar_date !== null && (
                  <button className="btn-primary mt-2 px-3 py-1 text-xs" onClick={() => onFix(warning)}>
                    {t("edit.fix")}
                  </button>
                )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
