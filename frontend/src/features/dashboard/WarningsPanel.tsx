import { useState } from "react";
import { SeverityBadge } from "@/components/ui";
import { blockingWarnings, warningsBySeverity } from "@/lib/schedule";
import type { ScheduleWarning } from "@/types/api";

export function WarningsPanel({ warnings }: { warnings: ScheduleWarning[] }) {
  const [showInfo, setShowInfo] = useState(false);
  const counts = warningsBySeverity(warnings);
  const blocking = blockingWarnings(warnings);

  if (warnings.length === 0) {
    return (
      <section className="card">
        <p className="text-sm text-emerald-700 dark:text-emerald-400">
          Every shift was filled with no rule broken.
        </p>
      </section>
    );
  }

  const shown = showInfo ? warnings : blocking;

  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="label mb-0">Warnings</h2>
        <div className="flex gap-2 text-xs text-slate-500">
          {counts.ERROR > 0 && <span>{counts.ERROR} needing attention</span>}
          {counts.WARNING > 0 && <span>{counts.WARNING} cautions</span>}
          {counts.INFO > 0 && <span>{counts.INFO} informational</span>}
        </div>
        {counts.INFO > 0 && (
          <button
            className="btn-ghost ml-auto text-xs"
            onClick={() => setShowInfo((value) => !value)}
          >
            {showInfo ? "Hide informational" : `Show ${counts.INFO} informational`}
          </button>
        )}
      </div>

      {blocking.length === 0 && !showInfo && (
        <p className="text-sm text-emerald-700 dark:text-emerald-400">
          Nothing needs attention. The remaining {counts.INFO} notes record where the
          rotation was relaxed to keep a shift staffed.
        </p>
      )}

      <ul className="max-h-72 space-y-1 overflow-auto">
        {shown.map((warning, index) => (
          <li
            key={`${warning.kind}-${warning.calendar_date}-${index}`}
            className="flex items-start gap-2 rounded-md border-l-2 px-3 py-1.5 text-sm"
            style={{
              borderLeftColor:
                warning.severity === "ERROR"
                  ? "#e11d48"
                  : warning.severity === "WARNING"
                    ? "#f59e0b"
                    : "#94a3b8",
            }}
          >
            <SeverityBadge severity={warning.severity} />
            <span className="flex-1">{warning.message}</span>
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
