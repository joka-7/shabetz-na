import { useState } from "react";
import { Plus } from "lucide-react";
import { api } from "@/api/client";
import {
  keys,
  useConfigMutation,
  useDivisions,
  useLevels,
  usePeople,
  useSkills,
} from "@/api/queries";
import { DivisionBadge, EmptyState, Spinner } from "@/components/ui";
import type { Person } from "@/types/api";
import { MutationError, Row, RowList, StepShell } from "./parts";

/** Monday-first labels; the stored value is JavaScript's weekday index. */
const WEEKDAYS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

export function PeopleStep() {
  const { data: people, isLoading } = usePeople();
  const { data: divisions } = useDivisions();
  const { data: skills } = useSkills();
  const { data: levels } = useLevels();

  const [fullName, setFullName] = useState("");
  const [divisionId, setDivisionId] = useState<number | null>(null);
  const [weekdays, setWeekdays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [personSkills, setPersonSkills] = useState<Record<number, number>>({});

  const create = useConfigMutation(
    (payload: unknown) => api.post<Person>("/api/config/people", payload),
    [keys.people],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/people/${id}`),
    [keys.people],
  );

  const resolvedDivision = divisionId ?? divisions?.[0]?.id ?? null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!fullName.trim() || resolvedDivision === null) return;
    create.mutate({
      full_name: fullName.trim(),
      division_id: resolvedDivision,
      working_weekdays: weekdays,
      skills: Object.entries(personSkills).map(([skill_id, level_id]) => ({
        skill_id: Number(skill_id),
        level_id,
      })),
    });
    setFullName("");
    setPersonSkills({});
  }

  if (!divisions?.length) {
    return (
      <StepShell title="People" intro="Add your roster.">
        <EmptyState
          title="Define divisions first"
          hint="Everyone belongs to a division, so those come first."
        />
      </StepShell>
    );
  }

  return (
    <StepShell
      title="People"
      intro="Add your roster, the days each person works, and what they are qualified to do."
    >
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label className="label" htmlFor="person-name">Full name</label>
            <input
              id="person-name"
              className="input"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="person-division">Division</label>
            <select
              id="person-division"
              className="input w-44"
              value={resolvedDivision ?? ""}
              onChange={(event) => setDivisionId(Number(event.target.value))}
            >
              {divisions.map((division) => (
                <option key={division.id} value={division.id}>{division.name}</option>
              ))}
            </select>
          </div>
        </div>

        <fieldset>
          <legend className="label">Works on</legend>
          <div className="flex flex-wrap gap-1">
            {WEEKDAYS.map((day) => {
              const checked = weekdays.includes(day.value);
              return (
                <label
                  key={day.value}
                  className={`btn cursor-pointer text-xs ${
                    checked
                      ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                      : "border border-slate-300 dark:border-slate-700"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={checked}
                    onChange={() =>
                      setWeekdays((days) =>
                        checked ? days.filter((d) => d !== day.value) : [...days, day.value],
                      )
                    }
                  />
                  {day.label}
                </label>
              );
            })}
          </div>
        </fieldset>

        {Boolean(skills?.length && levels?.length) && (
          <fieldset className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
            <legend className="label">Skills</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {skills!.map((skill) => (
                <div key={skill.id} className="flex items-center gap-2">
                  <span className="flex-1 truncate text-sm">{skill.name}</span>
                  <select
                    className="input w-36"
                    aria-label={`${skill.name} level`}
                    value={personSkills[skill.id] ?? ""}
                    onChange={(event) =>
                      setPersonSkills((current) => {
                        const next = { ...current };
                        if (!event.target.value) delete next[skill.id];
                        else next[skill.id] = Number(event.target.value);
                        return next;
                      })
                    }
                  >
                    <option value="">—</option>
                    {levels!.map((level) => (
                      <option key={level.id} value={level.id}>{level.name}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </fieldset>
        )}

        <button className="btn-primary" type="submit" disabled={create.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          Add person
        </button>
      </form>

      <MutationError error={create.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !people?.length ? (
        <EmptyState title="No people yet" hint="Add your roster to staff the jobs you defined." />
      ) : (
        <>
          <p className="text-xs text-slate-500">{people.length} people</p>
          <RowList>
            {people.slice(0, 40).map((person) => {
              const division = divisions.find((d) => d.id === person.division_id);
              return (
                <Row
                  key={person.id}
                  deleteLabel={`Remove ${person.full_name}`}
                  onDelete={() => remove.mutate(person.id)}
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium">{person.full_name}</span>
                    {division && <DivisionBadge id={division.id} name={division.name} />}
                    <span className="text-xs text-slate-500">
                      {person.working_weekdays
                        .map((d) => WEEKDAYS.find((w) => w.value === d)?.label)
                        .join(" ")}
                    </span>
                    <span className="text-xs text-slate-400">
                      {person.skills.length} skill{person.skills.length === 1 ? "" : "s"}
                    </span>
                  </div>
                </Row>
              );
            })}
          </RowList>
          {people.length > 40 && (
            <p className="text-xs text-slate-500">
              Showing the first 40; the rest are managed from the Configuration tab.
            </p>
          )}
        </>
      )}
    </StepShell>
  );
}
