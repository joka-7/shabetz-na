import { useEffect, useState } from "react";
import { Check, FileSpreadsheet, Plus } from "lucide-react";
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
import { useI18n } from "@/i18n";
import type { Person } from "@/types/api";
import { PeopleImport } from "./PeopleImport";
import {
  MutationError,
  Row,
  RowList,
  StepShell,
  WeekdayPicker,
  useDefaultWeek,
} from "./parts";

const SHOWN = 40;

export function PeopleStep() {
  const { t, tn, weekdayOrder, weekdayShort } = useI18n();
  const { data: people, isLoading } = usePeople();
  const { data: divisions } = useDivisions();
  const { data: skills } = useSkills();
  const { data: levels } = useLevels();
  const defaultWeek = useDefaultWeek();

  const [fullName, setFullName] = useState("");
  const [divisionId, setDivisionId] = useState<number | null>(null);
  const [weekdays, setWeekdays] = useState<number[]>(defaultWeek);
  const [personSkills, setPersonSkills] = useState<Record<number, number>>({});
  // Opened straight away while the roster is empty: that is when a spreadsheet
  // saves the most typing.
  const [importing, setImporting] = useState<boolean | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState<Person | null>(null);

  const create = useConfigMutation(
    (payload: unknown) => api.post<Person>("/api/config/people", payload),
    [keys.people],
  );
  const update = useConfigMutation(
    ({ id, ...payload }: { id: number } & Record<string, unknown>) =>
      api.put<Person>(`/api/config/people/${id}`, payload),
    [keys.people],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/people/${id}`),
    [keys.people],
  );

  const resolvedDivision = divisionId ?? divisions?.[0]?.id ?? null;
  // Decided once, when the roster first loads, so the panel does not vanish
  // (confirmation and all) the moment its own import fills the roster.
  useEffect(() => {
    if (importing === null && people) setImporting(people.length === 0);
  }, [importing, people]);
  const showImport = importing === true;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!fullName.trim() || resolvedDivision === null) return;
    const payload = {
      full_name: fullName.trim(),
      division_id: resolvedDivision,
      working_weekdays: weekdays,
      external_ref: editing?.external_ref ?? null,
      skills: Object.entries(personSkills).map(([skill_id, level_id]) => ({
        skill_id: Number(skill_id),
        level_id,
      })),
    };
    if (editing) update.mutate({ id: editing.id, ...payload });
    else create.mutate(payload);
    cancelEdit();
  }

  function startEdit(person: Person) {
    setEditing(person);
    setFullName(person.full_name);
    setDivisionId(person.division_id);
    setWeekdays(person.working_weekdays);
    setPersonSkills(Object.fromEntries(person.skills.map((s) => [s.skill_id, s.level_id])));
    document.getElementById("person-name")?.scrollIntoView({ block: "center" });
  }

  function cancelEdit() {
    setEditing(null);
    setFullName("");
    setPersonSkills({});
    setWeekdays(defaultWeek);
  }

  const days = (list: number[]) =>
    weekdayOrder.filter((d) => list.includes(d)).map(weekdayShort).join(" ");

  return (
    <StepShell title={t("section.people")} intro={t("people.intro")}>
      {showImport ? (
        <PeopleImport onClose={() => setImporting(false)} />
      ) : (
        <button className="btn-ghost" onClick={() => setImporting(true)}>
          <FileSpreadsheet className="h-4 w-4" aria-hidden />
          {t("people.importButton")}
        </button>
      )}

      {divisions?.length ? (
        <form onSubmit={submit} className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-48 flex-1">
              <label className="label" htmlFor="person-name">{t("people.fullName")}</label>
              <input
                id="person-name"
                className="input"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="person-division">{t("people.division")}</label>
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

          <WeekdayPicker legend={t("people.worksOn")} value={weekdays} onChange={setWeekdays} />

          {Boolean(skills?.length && levels?.length) && (
            <fieldset className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
              <legend className="label">{t("section.skills")}</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {skills!.map((skill) => (
                  <div key={skill.id} className="flex items-center gap-2">
                    <span className="flex-1 truncate text-sm">{skill.name}</span>
                    <select
                      className="input w-36"
                      aria-label={t("people.skillLevel", { skill: skill.name })}
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

          <div className="flex gap-2">
            <button
              className="btn-primary"
              type="submit"
              disabled={create.isPending || update.isPending}
            >
              {editing ? <Check className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
              {editing ? t("common.save") : t("people.add")}
            </button>
            {editing && (
              <button className="btn-ghost" type="button" onClick={cancelEdit}>
                {t("common.cancel")}
              </button>
            )}
          </div>
          {editing && (
            <p className="text-xs text-slate-500">{t("edit.editing", { name: editing.full_name })}</p>
          )}
        </form>
      ) : (
        // An import can create divisions as it goes; a single person needs one.
        <p className="text-xs text-slate-500">{t("people.noDivisionsHint")}</p>
      )}

      <MutationError error={create.error ?? remove.error ?? update.error} />

      {isLoading ? (
        <Spinner />
      ) : !people?.length ? (
        <EmptyState title={t("people.emptyTitle")} hint={t("people.emptyHint")} />
      ) : (
        <>
          <p className="text-xs text-slate-500">{tn("people.count", people.length)}</p>
          <RowList>
            {(showAll ? people : people.slice(0, SHOWN)).map((person) => {
              const division = divisions?.find((d) => d.id === person.division_id);
              return (
                <Row
                  key={person.id}
                  deleteLabel={t("common.removeNamed", { name: person.full_name })}
                  onDelete={() => remove.mutate(person.id)}
                  onEdit={() => startEdit(person)}
                  editLabel={t("common.editNamed", { name: person.full_name })}
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium">{person.full_name}</span>
                    {division && <DivisionBadge id={division.id} name={division.name} />}
                    <span className="text-xs text-slate-500">{days(person.working_weekdays)}</span>
                    <span className="text-xs text-slate-400">
                      {tn("people.skillCount", person.skills.length)}
                    </span>
                  </div>
                </Row>
              );
            })}
          </RowList>
          {people.length > SHOWN && !showAll && (
            <button className="btn-ghost text-xs" onClick={() => setShowAll(true)}>
              {t("people.showAll", { count: people.length })}
            </button>
          )}
        </>
      )}
    </StepShell>
  );
}
