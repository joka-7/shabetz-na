import { useMemo } from "react";
import { usePeople } from "@/api/queries";
import { DivisionBadge } from "@/components/ui";
import { useDivisions } from "@/api/queries";
import { useI18n } from "@/i18n";
import { fairnessRows, spread } from "@/lib/fairness";
import type { ScheduleRun } from "@/types/api";

/** Who is carrying how much, so an uneven schedule is visible before it is published. */
export function FairnessTable({ run }: { run: ScheduleRun }) {
  const { t } = useI18n();
  const { data: people = [] } = usePeople();
  const { data: divisions = [] } = useDivisions();
  const rows = useMemo(() => fairnessRows(run.assignments, people), [run.assignments, people]);
  const maxHours = Math.max(1, ...rows.map((r) => r.hours));

  const columns = [
    { key: "shifts", label: t("fairness.shifts"), values: rows.map((r) => r.shifts) },
    { key: "nights", label: t("fairness.nights"), values: rows.map((r) => r.nightShifts) },
    { key: "weekends", label: t("fairness.weekends"), values: rows.map((r) => r.weekendShifts) },
  ];

  return (
    <section className="card space-y-3">
      <p className="text-sm text-slate-500">{t("fairness.intro")}</p>
      <div className="flex flex-wrap gap-2">
        {columns.map((column) => (
          <span key={column.key} className="badge bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {t("fairness.spread", { what: column.label, gap: spread(column.values) })}
          </span>
        ))}
      </div>
      <div className="max-h-[32rem] overflow-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-white dark:bg-slate-900">
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th className="th">{t("table.person")}</th>
              <th className="th">{t("table.division")}</th>
              <th className="th">{t("fairness.hours")}</th>
              {columns.map((column) => (
                <th key={column.key} className="th">{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.personId} className="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
                <td className="td font-medium">{row.name}</td>
                <td className="td">
                  <DivisionBadge
                    id={row.divisionId}
                    name={divisions.find((d) => d.id === row.divisionId)?.name ?? `#${row.divisionId}`}
                  />
                </td>
                <td className="td">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-28 rounded bg-slate-100 dark:bg-slate-800" aria-hidden>
                      <div
                        className="h-2 rounded bg-slate-500"
                        style={{ width: `${(row.hours / maxHours) * 100}%` }}
                      />
                    </div>
                    <span className="tabular-nums">{Math.round(row.hours * 10) / 10}</span>
                  </div>
                </td>
                <td className="td tabular-nums">{row.shifts}</td>
                <td className="td tabular-nums">{row.nightShifts}</td>
                <td className="td tabular-nums">{row.weekendShifts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
