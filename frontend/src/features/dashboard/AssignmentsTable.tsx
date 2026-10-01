import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, Lock, Pencil, Search, Unlock } from "lucide-react";
import { Avatar, DivisionBadge, EmptyState } from "@/components/ui";
import {
  crossesMidnight,
  emptyFilters,
  filterAssignments,
  shiftWindow,
  type AssignmentFilters,
} from "@/lib/schedule";
import { useI18n } from "@/i18n";
import type { Assignment, Division, ScheduleRun } from "@/types/api";

const helper = createColumnHelper<Assignment>();

export function AssignmentsTable({
  run,
  divisions,
  onEdit,
  onToggleLock,
}: {
  run: ScheduleRun;
  divisions: Division[];
  /** Present only for roles that may change a schedule. */
  onEdit?: (assignment: Assignment) => void;
  /** Pin or release a shift; pinned shifts survive regeneration. */
  onToggleLock?: (assignment: Assignment) => void;
}) {
  const { t, formatDate } = useI18n();
  const [filters, setFilters] = useState<AssignmentFilters>(emptyFilters);
  const [sorting, setSorting] = useState<SortingState>([
    { id: "calendar_date", desc: false },
  ]);

  const divisionName = useMemo(
    () => new Map(divisions.map((division) => [division.id, division.name])),
    [divisions],
  );

  const jobs = useMemo(() => {
    const seen = new Map<number, string>();
    for (const assignment of run.assignments) seen.set(assignment.job_id, assignment.job_name);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [run.assignments]);

  const dates = useMemo(
    () => [...new Set(run.assignments.map((a) => a.calendar_date))].sort(),
    [run.assignments],
  );

  const rows = useMemo(
    () => filterAssignments(run.assignments, filters),
    [run.assignments, filters],
  );

  const columns = useMemo(
    () => [
      helper.accessor("calendar_date", {
        header: t("table.date"),
        cell: ({ getValue }) => (
          <span className="whitespace-nowrap">
            {formatDate(getValue(), { weekday: "short", day: "numeric", month: "short" })}
          </span>
        ),
      }),
      helper.accessor("template_name", { header: t("table.window") }),
      helper.display({
        id: "time",
        header: t("table.time"),
        cell: ({ row }) => (
          <span className="whitespace-nowrap font-medium tabular-nums text-indigo-700 dark:text-indigo-300" dir="ltr">
            {shiftWindow(row.original)}
            {crossesMidnight(row.original) && (
              <span className="ms-1 text-xs text-slate-400" title={t("table.nextDay")}>
                +1
              </span>
            )}
          </span>
        ),
      }),
      helper.accessor("job_name", { header: t("table.job") }),
      helper.accessor("person_name", {
        header: t("table.person"),
        cell: ({ row }) => (
          <span className="flex items-center gap-2">
            <Avatar name={row.original.person_name} id={row.original.division_id} size="sm" />
            <span className="font-medium">{row.original.person_name}</span>
            {row.original.role === "ROLE" && (
              <span
                className="badge bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300"
                title={t("table.roleHint")}
              >
                {t("table.role")}
              </span>
            )}
            {row.original.is_manual && (
              <span
                className="badge bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-300"
                title={t("edit.manualHint")}
              >
                {t("edit.manual")}
              </span>
            )}
            {row.original.is_division_fallback && (
              <span
                className="badge bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300"
                title={t("stat.borrowedHint")}
              >
                {t("table.borrowed")}
              </span>
            )}
          </span>
        ),
      }),
      helper.accessor("division_id", {
        header: t("table.division"),
        cell: ({ getValue }) => {
          const id = getValue();
          return <DivisionBadge id={id} name={divisionName.get(id) ?? `#${id}`} />;
        },
      }),
      ...(onEdit
        ? [
            helper.display({
              id: "actions",
              header: t("edit.actions"),
              cell: ({ row }) => (
                <div className="flex gap-1">
                  <button
                    className="btn-ghost p-1.5"
                    onClick={() => onEdit(row.original)}
                    aria-label={t("edit.changeNamed", { name: row.original.person_name })}
                    title={t("edit.change")}
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden />
                  </button>
                  {onToggleLock && (
                    <button
                      className="btn-ghost p-1.5"
                      onClick={() => onToggleLock(row.original)}
                      aria-pressed={Boolean(row.original.is_locked)}
                      aria-label={
                        row.original.is_locked
                          ? t("edit.unlockNamed", { name: row.original.person_name })
                          : t("edit.lockNamed", { name: row.original.person_name })
                      }
                      title={row.original.is_locked ? t("edit.lockedHint") : t("edit.lockHint")}
                    >
                      {row.original.is_locked ? (
                        <Lock className="h-3.5 w-3.5" aria-hidden />
                      ) : (
                        <Unlock className="h-3.5 w-3.5 text-slate-400" aria-hidden />
                      )}
                    </button>
                  )}
                </div>
              ),
            }),
          ]
        : []),
    ],
    [divisionName, t, formatDate, onEdit, onToggleLock],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <section className="card">
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <div className="min-w-48 flex-1">
          <label className="label" htmlFor="assignment-search">{t("table.search")}</label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute start-2 top-2.5 h-4 w-4 text-slate-400"
              aria-hidden
            />
            <input
              id="assignment-search"
              className="input ps-8"
              placeholder={t("table.searchPlaceholder")}
              value={filters.search}
              onChange={(event) => setFilters({ ...filters, search: event.target.value })}
            />
          </div>
        </div>

        <div>
          <label className="label" htmlFor="filter-division">{t("table.division")}</label>
          <select
            id="filter-division"
            className="input w-40"
            value={filters.divisionId ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                divisionId: event.target.value ? Number(event.target.value) : null,
              })
            }
          >
            <option value="">{t("table.all")}</option>
            {divisions.map((division) => (
              <option key={division.id} value={division.id}>{division.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="filter-job">{t("table.job")}</label>
          <select
            id="filter-job"
            className="input w-44"
            value={filters.jobId ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                jobId: event.target.value ? Number(event.target.value) : null,
              })
            }
          >
            <option value="">{t("table.all")}</option>
            {jobs.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="filter-date">{t("table.date")}</label>
          <select
            id="filter-date"
            className="input w-40"
            value={filters.date ?? ""}
            onChange={(event) =>
              setFilters({ ...filters, date: event.target.value || null })
            }
          >
            <option value="">{t("table.all")}</option>
            {dates.map((date) => (
              <option key={date} value={date}>
                {formatDate(date, { weekday: "short", day: "numeric", month: "short" })}
              </option>
            ))}
          </select>
        </div>

        {(filters.search || filters.divisionId || filters.jobId || filters.date) && (
          <button className="btn-ghost" onClick={() => setFilters(emptyFilters)}>
            {t("table.clear")}
          </button>
        )}
      </div>

      <p className="mb-2 text-xs text-slate-500">
        {t("table.count", { shown: rows.length, total: run.assignments.length })}
      </p>

      {rows.length === 0 ? (
        <EmptyState title={t("table.noMatch")} />
      ) : (
        <div className="max-h-[32rem] overflow-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-white dark:bg-slate-800">
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id} className="border-b border-slate-200 dark:border-slate-800">
                  {group.headers.map((header) => {
                    const sorted = header.column.getIsSorted();
                    return (
                      <th key={header.id} className="th">
                        {header.column.getCanSort() ? (
                          <button
                            className="flex items-center gap-1 uppercase"
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            {flexRender(header.column.columnDef.header, header.getContext())}
                            {sorted === "asc" && <ArrowUp className="h-3 w-3" aria-hidden />}
                            {sorted === "desc" && <ArrowDown className="h-3 w-3" aria-hidden />}
                          </button>
                        ) : (
                          flexRender(header.column.columnDef.header, header.getContext())
                        )}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-slate-100 last:border-0 hover:bg-indigo-50/40 dark:border-slate-700/60 dark:hover:bg-slate-700/30"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="td">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
