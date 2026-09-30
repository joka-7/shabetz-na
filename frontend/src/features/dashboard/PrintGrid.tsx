import { useMemo } from "react";
import { useI18n } from "@/i18n";
import { buildWeeks } from "@/lib/printGrid";
import type { ScheduleRun } from "@/types/api";

/** Only visible on paper: the weekly wall chart people still pin up. */
export function PrintGrid({ run, projectName }: { run: ScheduleRun; projectName: string }) {
  const { t, formatDate } = useI18n();
  const from = String(run.params.start_date ?? "");
  const to = String(run.params.end_date ?? "");
  const weeks = useMemo(() => buildWeeks(run.assignments, from, to), [run.assignments, from, to]);

  return (
    <div className="hidden text-black print:block">
      <h1 className="mb-1 text-xl font-semibold">{projectName}</h1>
      <p className="mb-4 text-sm">
        {formatDate(from)} – {formatDate(to)}
      </p>
      {weeks.map((week) => (
        <table key={week.dates[0]} className="mb-6 w-full border-collapse text-xs [break-inside:avoid]">
          <thead>
            <tr>
              <th className="border border-slate-400 p-1 text-start">{t("table.job")}</th>
              {week.dates.map((date) => (
                <th key={date} className="border border-slate-400 p-1">
                  {formatDate(date, { weekday: "short", day: "numeric", month: "numeric" })}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {week.rows.map((row) => (
              <tr key={row.key}>
                <td className="border border-slate-400 p-1 font-medium">
                  {row.job}
                  <div className="font-normal text-slate-600">{row.window}</div>
                </td>
                {week.dates.map((date) => (
                  <td key={date} className="border border-slate-400 p-1 align-top">
                    {(row.cells[date] ?? []).map((name) => (
                      <div key={name}>{name}</div>
                    ))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  );
}
