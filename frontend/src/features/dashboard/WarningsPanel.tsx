import { useState } from "react";
import { SeverityBadge } from "@/components/ui";
import { useI18n } from "@/i18n";
import { blockingWarnings, warningsBySeverity } from "@/lib/schedule";
import type { ScheduleWarning } from "@/types/api";

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
    return warning.message;
  };
}

export function WarningsPanel({ warnings }: { warnings: ScheduleWarning[] }) {
  const { t } = useI18n();
  const text = useWarningText();
  const [showInfo, setShowInfo] = useState(false);
  const counts = warningsBySeverity(warnings);
  const blocking = blockingWarnings(warnings);

  if (warnings.length === 0) {
    return (
      <section className="card">
        <p className="text-sm text-emerald-700 dark:text-emerald-400">{t("warnings.none")}</p>
      </section>
    );
  }

  const shown = showInfo ? warnings : blocking;

  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="label mb-0">{t("stat.warnings")}</h2>
        <div className="flex gap-2 text-xs text-slate-500">
          {counts.ERROR > 0 && <span>{t("warnings.errors", { count: counts.ERROR })}</span>}
          {counts.WARNING > 0 && <span>{t("warnings.cautions", { count: counts.WARNING })}</span>}
          {counts.INFO > 0 && <span>{t("warnings.info", { count: counts.INFO })}</span>}
        </div>
        {counts.INFO > 0 && (
          <button
            className="btn-ghost ms-auto text-xs"
            onClick={() => setShowInfo((value) => !value)}
          >
            {showInfo ? t("warnings.hideInfo") : t("warnings.showInfo", { count: counts.INFO })}
          </button>
        )}
      </div>

      {blocking.length === 0 && !showInfo && (
        <p className="text-sm text-emerald-700 dark:text-emerald-400">
          {t("warnings.onlyInfo", { count: counts.INFO })}
        </p>
      )}

      <ul className="max-h-72 space-y-1 overflow-auto">
        {shown.map((warning, index) => (
          <li
            key={`${warning.kind}-${warning.calendar_date}-${index}`}
            className="flex items-start gap-2 rounded-md border-s-2 px-3 py-1.5 text-sm"
            style={{
              borderInlineStartColor:
                warning.severity === "ERROR"
                  ? "#e11d48"
                  : warning.severity === "WARNING"
                    ? "#f59e0b"
                    : "#94a3b8",
            }}
          >
            <SeverityBadge severity={warning.severity} />
            <span className="flex-1">{text(warning)}</span>
            {warning.required !== null && warning.assigned !== null && (
              <span className="shrink-0 text-xs tabular-nums text-slate-500">
                {warning.assigned}/{warning.required}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
