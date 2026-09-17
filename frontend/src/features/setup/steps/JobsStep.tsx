import { useState } from "react";
import { Plus, X } from "lucide-react";
import { api } from "@/api/client";
import {
  keys,
  useConfigMutation,
  useJobs,
  useLevels,
  useSkills,
  useTemplates,
} from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import type { DivisionPolicy, Job } from "@/types/api";
import { MutationError, Row, RowList, StepShell } from "./parts";

interface DraftRequirement {
  skill_id: number;
  min_level_id: number;
  /** null means every person on the shift; a number means at least that many. */
  required_count: number | null;
  is_leadership: boolean;
}

const POLICY_LABELS: Record<DivisionPolicy, string> = {
  ACTIVE_DIVISION_PREFERRED: "Prefer the division on duty, borrow if short",
  ACTIVE_DIVISION_ONLY: "Only the division on duty",
  ANY_DIVISION: "Anyone, ignoring the rotation",
};

export function JobsStep() {
  const { data: jobs, isLoading } = useJobs();
  const { data: templates } = useTemplates();
  const { data: skills } = useSkills();
  const { data: levels } = useLevels();

  const [name, setName] = useState("");
  const [headcount, setHeadcount] = useState(1);
  const [policy, setPolicy] = useState<DivisionPolicy>("ACTIVE_DIVISION_PREFERRED");
  const [templateIds, setTemplateIds] = useState<number[]>([]);
  const [requirements, setRequirements] = useState<DraftRequirement[]>([]);

  const create = useConfigMutation(
    (payload: unknown) => api.post<Job>("/api/config/jobs", payload),
    [keys.jobs],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/jobs/${id}`),
    [keys.jobs],
  );

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || templateIds.length === 0) return;
    create.mutate({
      name: name.trim(),
      required_people_per_shift: headcount,
      division_policy: policy,
      shift_template_ids: templateIds,
      requirements,
    });
    setName("");
    setTemplateIds([]);
    setRequirements([]);
    setHeadcount(1);
  }

  const canBuildRequirements = Boolean(skills?.length && levels?.length);

  return (
    <StepShell
      title="Jobs"
      intro="Define the work to be staffed: how many people per shift, which windows it runs, and what they must be qualified to do."
    >
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label className="label" htmlFor="job-name">Job name</label>
            <input
              id="job-name"
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="job-headcount">People per shift</label>
            <input
              id="job-headcount"
              className="input w-28"
              type="number"
              min={1}
              value={headcount}
              onChange={(event) => setHeadcount(Number(event.target.value))}
            />
          </div>
        </div>

        <div>
          <label className="label" htmlFor="job-policy">Who may be assigned</label>
          <select
            id="job-policy"
            className="input"
            value={policy}
            onChange={(event) => setPolicy(event.target.value as DivisionPolicy)}
          >
            {Object.entries(POLICY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <fieldset>
          <legend className="label">Shift windows this job runs</legend>
          {!templates?.length ? (
            <p className="text-xs text-slate-500">Define shift windows first.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {templates.map((template) => {
                const checked = templateIds.includes(template.id);
                return (
                  <label
                    key={template.id}
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
                        setTemplateIds((ids) =>
                          checked ? ids.filter((id) => id !== template.id) : [...ids, template.id],
                        )
                      }
                    />
                    {template.name}
                  </label>
                );
              })}
            </div>
          )}
        </fieldset>

        {canBuildRequirements && (
          <RequirementBuilder
            skills={skills!}
            levels={levels!}
            requirements={requirements}
            onChange={setRequirements}
          />
        )}

        <button
          className="btn-primary"
          type="submit"
          disabled={create.isPending || !templateIds.length || !name.trim()}
        >
          <Plus className="h-4 w-4" aria-hidden />
          Add job
        </button>
      </form>

      <MutationError error={create.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !jobs?.length ? (
        <EmptyState title="No jobs yet" hint="A job needs at least one shift window." />
      ) : (
        <RowList>
          {jobs.map((job) => (
            <Row
              key={job.id}
              deleteLabel={`Remove ${job.name}`}
              onDelete={() => remove.mutate(job.id)}
            >
              <div>
                <div className="text-sm font-medium">{job.name}</div>
                <div className="text-xs text-slate-500">
                  {job.required_people_per_shift} per shift ·{" "}
                  {job.shift_template_ids.length} window
                  {job.shift_template_ids.length === 1 ? "" : "s"} ·{" "}
                  {POLICY_LABELS[job.division_policy].toLowerCase()}
                </div>
                {job.requirements.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {job.requirements.map((requirement) => (
                      <span
                        key={requirement.id}
                        className="badge bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                      >
                        {requirement.required_count === null
                          ? `all: ${requirement.skill_name}`
                          : `${requirement.required_count}× ${requirement.skill_name}`}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </Row>
          ))}
        </RowList>
      )}
    </StepShell>
  );
}

/**
 * Builds the two kinds of staffing rule.
 *
 * "Everyone" rules gate who may fill the shift at all; "at least N" rules are
 * the named roles, filled first so the one qualified person is not spent as
 * general cover.
 */
function RequirementBuilder({
  skills,
  levels,
  requirements,
  onChange,
}: {
  skills: { id: number; name: string }[];
  levels: { id: number; name: string; rank: number }[];
  requirements: DraftRequirement[];
  onChange: (next: DraftRequirement[]) => void;
}) {
  const [skillId, setSkillId] = useState(skills[0]?.id ?? 0);
  const [levelId, setLevelId] = useState(levels[0]?.id ?? 0);
  const [mode, setMode] = useState<"all" | "count">("all");
  const [count, setCount] = useState(1);

  function add() {
    onChange([
      ...requirements,
      {
        skill_id: skillId,
        min_level_id: levelId,
        required_count: mode === "all" ? null : count,
        is_leadership: mode === "count",
      },
    ]);
  }

  const nameOf = (id: number) => skills.find((s) => s.id === id)?.name ?? "?";
  const levelOf = (id: number) => levels.find((l) => l.id === id)?.name ?? "?";

  return (
    <fieldset className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
      <legend className="label">Staffing requirements</legend>

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="label" htmlFor="req-mode">Applies to</label>
          <select
            id="req-mode"
            className="input w-44"
            value={mode}
            onChange={(event) => setMode(event.target.value as "all" | "count")}
          >
            <option value="all">Everyone on the shift</option>
            <option value="count">At least this many</option>
          </select>
        </div>
        {mode === "count" && (
          <div>
            <label className="label" htmlFor="req-count">How many</label>
            <input
              id="req-count"
              className="input w-20"
              type="number"
              min={1}
              value={count}
              onChange={(event) => setCount(Number(event.target.value))}
            />
          </div>
        )}
        <div>
          <label className="label" htmlFor="req-skill">Skill</label>
          <select
            id="req-skill"
            className="input w-40"
            value={skillId}
            onChange={(event) => setSkillId(Number(event.target.value))}
          >
            {skills.map((skill) => (
              <option key={skill.id} value={skill.id}>{skill.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="req-level">At least</label>
          <select
            id="req-level"
            className="input w-36"
            value={levelId}
            onChange={(event) => setLevelId(Number(event.target.value))}
          >
            {levels.map((level) => (
              <option key={level.id} value={level.id}>{level.name}</option>
            ))}
          </select>
        </div>
        <button className="btn-ghost" type="button" onClick={add}>
          <Plus className="h-4 w-4" aria-hidden />
          Add rule
        </button>
      </div>

      {requirements.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1">
          {requirements.map((requirement, index) => (
            <li
              key={index}
              className="badge gap-1 bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
            >
              {requirement.required_count === null
                ? "everyone"
                : `${requirement.required_count}×`}{" "}
              {nameOf(requirement.skill_id)} ≥ {levelOf(requirement.min_level_id)}
              <button
                type="button"
                onClick={() => onChange(requirements.filter((_, i) => i !== index))}
                aria-label="Remove this rule"
              >
                <X className="h-3 w-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}
