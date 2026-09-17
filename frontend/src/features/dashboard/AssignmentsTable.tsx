import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { DivisionBadge, EmptyState } from "@/components/ui";
import {
  crossesMidnight,
  emptyFilters,
  filterAssignments,
  shiftWindow,
  type AssignmentFilters,
} from "@/lib/schedule";
import type { Assignment, Division, ScheduleRun } from "@/types/api";

const helper = createColumnHelper<Assignment>();

export function AssignmentsTable({
  run,
  divisions,
}: {
  run: ScheduleRun;
  divisions: Division[];
}) {
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
      helper.accessor("calendar_date", { header: "Date" }),
      helper.accessor("template_name", { header: "Window" }),
      helper.display({
        id: "time",
        header: "Time",
        cell: ({ row }) => (
          <span className="tabular-nums">
            {shiftWindow(row.original)}
            {crossesMidnight(row.original) && (
              <span className="ml-1 text-xs text-slate-400" title="Ends the next day">
                +1
              </span>
            )}
          </span>
        ),
      }),
      helper.accessor("job_name", { header: "Job" }),
      helper.accessor("person_name", {
        header: "Person",
        cell: ({ row }) => (
          <span className="flex items-center gap-1.5">
            {row.original.person_name}
            {row.original.role === "ROLE" && (
              <span
                className="badge bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300"
                title="Fills a named role requirement"
              >
                role
              </span>
            )}
            {row.original.is_division_fallback && (
              <span
                className="badge bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300"
                title="Borrowed from outside the division on duty"
              >
                borrowed
              </span>
            )}
          </span>
        ),
      }),
      helper.accessor("division_id", {
        header: "Division",
        cell: ({ getValue }) => {
          const id = getValue();
          return <DivisionBadge id={id} name={divisionName.get(id) ?? `Division ${id}`} />;
        },
      }),
    ],
    [divisionName],
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
          <label className="label" htmlFor="assignment-search">Search</label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-slate-400"
              aria-hidden
            />
            <input
              id="assignment-search"
              className="input pl-8"
              placeholder="Person, job or window"
              value={filters.search}
              onChange={(event) => setFilters({ ...filters, search: event.target.value })}
            />
          </div>
        </div>

        <div>
          <label className="label" htmlFor="filter-division">Division</label>
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
            <option value="">All</option>
            {divisions.map((division) => (
              <option key={division.id} value={division.id}>{division.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="filter-job">Job</label>
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
            <option value="">All</option>
            {jobs.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="filter-date">Date</label>
          <select
            id="filter-date"
            className="input w-40"
            value={filters.date ?? ""}
            onChange={(event) =>
              setFilters({ ...filters, date: event.target.value || null })
            }
          >
            <option value="">All</option>
            {dates.map((date) => (
              <option key={date} value={date}>{date}</option>
            ))}
          </select>
        </div>

        {(filters.search || filters.divisionId || filters.jobId || filters.date) && (
          <button className="btn-ghost" onClick={() => setFilters(emptyFilters)}>
            Clear
          </button>
        )}
      </div>

      <p className="mb-2 text-xs text-slate-500">
        {rows.length} of {run.assignments.length} shifts
      </p>

      {rows.length === 0 ? (
        <EmptyState title="Nothing matches these filters" />
      ) : (
        <div className="max-h-[32rem] overflow-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-white dark:bg-slate-900">
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
                  className="border-b border-slate-100 last:border-0 dark:border-slate-800/60"
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
