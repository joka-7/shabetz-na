import { useFeasibility } from "@/api/queries";
import { EmptyState, Spinner, VerdictBadge } from "@/components/ui";
import { clockTime } from "@/lib/schedule";

/**
 * Shows whether the configured jobs can actually be staffed.
 *
 * The number that matters is the distinct-people floor, not the peak. When the
 * rest window forces two shift windows to use different crews, their head
 * counts add rather than overlap -- so a configuration can need far more people
 * than the busiest single moment suggests.
 */
export function FeasibilityPanel() {
  const { data, isLoading, error } = useFeasibility();

  if (isLoading) return <Spinner label="Checking whether this can be staffed…" />;
  if (error || !data) {
    return <EmptyState title="Could not check feasibility" hint="Try again once jobs exist." />;
  }

  if (data.person_shifts_per_day === 0) {
    return (
      <EmptyState
        title="No jobs configured yet"
        hint="Add a job with at least one shift window to see whether it can be staffed."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <VerdictBadge verdict={data.verdict} />
        {data.messages.map((message) => (
          <p key={message} className="text-sm text-slate-600 dark:text-slate-400">
            {message}
          </p>
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Figure label="Person-shifts per day" value={data.person_shifts_per_day} />
        <Figure
          label="Busiest moment"
          value={data.peak_concurrent_people}
          hint="people on duty at once"
        />
        <Figure
          label="Distinct people needed"
          value={data.minimum_distinct_needed}
          hint="per duty day, after rest"
          emphasis
        />
      </div>

      {data.minimum_distinct_needed > data.peak_concurrent_people && (
        <p className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          The floor of {data.minimum_distinct_needed} exceeds the busiest moment of{" "}
          {data.peak_concurrent_people} because the rest window stops one crew covering
          consecutive windows, so those head counts add together.
        </p>
      )}

      <div>
        <h3 className="label">Coverage by window</h3>
        <div className="space-y-1">
          {data.window_demand.map((window) => (
            <div key={window.template_id} className="flex items-center gap-2 text-sm">
              <span className="w-28 shrink-0 truncate text-slate-500">
                {window.template_name}
              </span>
              <span className="w-28 shrink-0 tabular-nums text-xs text-slate-500">
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
              <span className="w-8 shrink-0 text-right tabular-nums text-sm">
                {window.concurrent_people}
              </span>
            </div>
          ))}
        </div>
      </div>

      {data.divisions.length > 0 && (
        <div>
          <h3 className="label">By division</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="th">Division</th>
                  <th className="th">People</th>
                  <th className="th">Available/day</th>
                  <th className="th">Needed</th>
                  <th className="th">Verdict</th>
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

          {data.divisions.flatMap((d) => d.messages).length > 0 && (
            <ul className="mt-2 space-y-1">
              {data.divisions.flatMap((division) =>
                division.messages.map((message) => (
                  <li
                    key={`${division.division_id}-${message}`}
                    className="rounded-md border-l-2 border-amber-400 bg-amber-50 px-3 py-1.5 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
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
