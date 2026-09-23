import { useFeasibility, useLevels } from "@/api/queries";
import { EmptyState, Spinner, VerdictBadge } from "@/components/ui";
import { useI18n } from "@/i18n";
import { clockTime } from "@/lib/schedule";
import type { DivisionFeasibility, Feasibility } from "@/types/api";

/**
 * Shows whether the configured jobs can actually be staffed.
 *
 * The number that matters is the distinct-people floor, not the peak. When the
 * rest window forces two shift windows to use different crews, their head
 * counts add rather than overlap -- so a configuration can need far more people
 * than the busiest single moment suggests.
 */
export function FeasibilityPanel() {
  const { t } = useI18n();
  const { data, isLoading, error } = useFeasibility();
  const { data: levels } = useLevels();

  if (isLoading) return <Spinner label={t("feasibility.checking")} />;
  if (error || !data) {
    return <EmptyState title={t("feasibility.failed")} hint={t("feasibility.failedHint")} />;
  }

  if (data.person_shifts_per_day === 0) {
    return <EmptyState title={t("feasibility.noJobs")} hint={t("feasibility.noJobsHint")} />;
  }

  // Worded here from the figures rather than taken from the server's English,
  // so the explanation follows the interface language.
  const overall = overallMessage(data, t);
  const levelName = (rank: number) =>
    levels?.find((level) => level.rank === rank)?.name ??
    levels?.find((level) => level.rank > rank)?.name ??
    String(rank);
  const divisionMessages = (division: DivisionFeasibility): string[] => [
    ...(division.minimum_distinct_needed > 0 &&
    division.expected_available < division.minimum_distinct_needed
      ? [
          t("feasibility.divisionShort", {
            division: division.division_name,
            people: division.headcount,
            available: division.expected_available.toFixed(1),
            needed: division.minimum_distinct_needed,
          }),
        ]
      : []),
    ...division.skill_floors
      .filter((floor) => !floor.satisfied)
      .map((floor) =>
        t("feasibility.skillShort", {
          division: division.division_name,
          needed: floor.needed_distinct,
          skill: floor.skill_name,
          level: levelName(floor.min_rank),
          available: floor.available,
        }),
      ),
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <VerdictBadge verdict={data.verdict} />
        {overall && <p className="text-sm text-slate-600 dark:text-slate-400">{overall}</p>}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Figure label={t("feasibility.personShifts")} value={data.person_shifts_per_day} />
        <Figure
          label={t("feasibility.peak")}
          value={data.peak_concurrent_people}
          hint={t("feasibility.peakHint")}
        />
        <Figure
          label={t("feasibility.distinct")}
          value={data.minimum_distinct_needed}
          hint={t("feasibility.distinctHint")}
          emphasis
        />
      </div>

      {data.minimum_distinct_needed > data.peak_concurrent_people && (
        <p className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          {t("feasibility.floorExplained", {
            floor: data.minimum_distinct_needed,
            peak: data.peak_concurrent_people,
          })}
        </p>
      )}

      <div>
        <h3 className="label">{t("feasibility.coverage")}</h3>
        <div className="space-y-1">
          {data.window_demand.map((window) => (
            <div key={window.template_id} className="flex items-center gap-2 text-sm">
              <span className="w-28 shrink-0 truncate text-slate-500">
                {window.template_name}
              </span>
              <span className="w-28 shrink-0 tabular-nums text-xs text-slate-500" dir="ltr">
                {clockTime(window.start_hour)}–
                {clockTime(window.start_hour + window.duration_hours)}
              </span>
              <div className="h-4 flex-1 rounded bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-4 rounded bg-slate-400 dark:bg-slate-600"
                  style={{
                    width: `${Math.min(100, (window.concurrent_people / Math.max(1, data.peak_concurrent_people)) * 100)}%`,
                  }}
                />
              </div>
              <span className="w-8 shrink-0 text-end tabular-nums text-sm">
                {window.concurrent_people}
              </span>
            </div>
          ))}
        </div>
      </div>

      {data.divisions.length > 0 && (
        <div>
          <h3 className="label">{t("feasibility.byDivision")}</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="th">{t("table.division")}</th>
                  <th className="th">{t("section.people")}</th>
                  <th className="th">{t("feasibility.availablePerDay")}</th>
                  <th className="th">{t("feasibility.needed")}</th>
                  <th className="th">{t("feasibility.verdict")}</th>
                </tr>
              </thead>
              <tbody>
                {data.divisions.map((division) => (
                  <tr
                    key={division.division_id}
                    className="border-b border-slate-100 dark:border-slate-800/60"
                  >
                    <td className="td">{division.division_name}</td>
                    <td className="td tabular-nums">{division.headcount}</td>
                    <td className="td tabular-nums">
                      {division.expected_available.toFixed(1)}
                    </td>
                    <td className="td tabular-nums">{division.minimum_distinct_needed}</td>
                    <td className="td">
                      <VerdictBadge verdict={division.verdict} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.divisions.flatMap(divisionMessages).length > 0 && (
            <ul className="mt-2 space-y-1">
              {data.divisions.flatMap((division) =>
                divisionMessages(division).map((message) => (
                  <li
                    key={`${division.division_id}-${message}`}
                    className="rounded-md border-s-2 border-amber-400 bg-amber-50 px-3 py-1.5 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
                  >
                    {message}
                  </li>
                )),
              )}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Figure({
  label,
  value,
  hint,
  emphasis,
}: {
  label: string;
  value: number;
  hint?: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`rounded-md border p-3 ${
        emphasis
          ? "border-slate-400 dark:border-slate-600"
          : "border-slate-200 dark:border-slate-800"
      }`}
    >
      <div className="label">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

function overallMessage(
  data: Feasibility,
  t: ReturnType<typeof useI18n>["t"],
): string | null {
  const params = { needed: data.minimum_distinct_needed, shifts: data.person_shifts_per_day };
  if (data.verdict === "INFEASIBLE") return t("feasibility.overallInfeasible", params);
  if (data.verdict === "TIGHT") return t("feasibility.overallTight", params);
  return null;
}
