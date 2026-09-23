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
import { useI18n } from "@/i18n";
import type { DivisionPolicy, Job } from "@/types/api";
import { MutationError, Row, RowList, StepShell } from "./parts";

interface DraftRequirement {
  skill_id: number;
  min_level_id: number;
  /** null means every person on the shift; a number means at least that many. */
  required_count: number | null;
  is_leadership: boolean;
}

const POLICIES: DivisionPolicy[] = [
  "ACTIVE_DIVISION_PREFERRED",
  "ACTIVE_DIVISION_ONLY",
  "ANY_DIVISION",
];

export function JobsStep() {
  const { t, tn } = useI18n();
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
    <StepShell title={t("section.jobs")} intro={t("jobs.intro")}>
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label className="label" htmlFor="job-name">{t("jobs.name")}</label>
            <input
              id="job-name"
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="job-headcount">{t("jobs.headcount")}</label>
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
          <label className="label" htmlFor="job-policy">{t("jobs.policy")}</label>
          <select
            id="job-policy"
            className="input"
            value={policy}
            onChange={(event) => setPolicy(event.target.value as DivisionPolicy)}
          >
            {POLICIES.map((value) => (
              <option key={value} value={value}>
                {t(`policy.${value}`)}
              </option>
            ))}
          </select>
        </div>

        <fieldset>
          <legend className="label">{t("jobs.windows")}</legend>
          {!templates?.length ? (
            <p className="text-xs text-slate-500">{t("jobs.windowsFirst")}</p>
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
          {t("jobs.add")}
        </button>
      </form>

      <MutationError error={create.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !jobs?.length ? (
        <EmptyState title={t("jobs.emptyTitle")} hint={t("jobs.emptyHint")} />
      ) : (
        <RowList>
          {jobs.map((job) => (
            <Row
              key={job.id}
              deleteLabel={t("common.removeNamed", { name: job.name })}
              onDelete={() => remove.mutate(job.id)}
            >
              <div>
                <div className="text-sm font-medium">{job.name}</div>
                <div className="text-xs text-slate-500">
                  {[
                    t("jobs.perShift", { count: job.required_people_per_shift }),
                    tn("jobs.windowCount", job.shift_template_ids.length),
                    t(`policy.${job.division_policy}`),
                  ].join(" · ")}
                </div>
                {job.requirements.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {job.requirements.map((requirement) => (
                      <span
                        key={requirement.id}
                        className="badge bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                      >
                        {requirement.required_count === null
                          ? t("jobs.reqEveryone", { skill: requirement.skill_name ?? "" })
                          : t("jobs.reqCount", {
                              count: requirement.required_count,
                              skill: requirement.skill_name ?? "",
                            })}
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
  const { t } = useI18n();
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
      <legend className="label">{t("jobs.requirements")}</legend>

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="label" htmlFor="req-mode">{t("jobs.appliesTo")}</label>
          <select
            id="req-mode"
            className="input w-44"
            value={mode}
            onChange={(event) => setMode(event.target.value as "all" | "count")}
          >
            <option value="all">{t("jobs.modeAll")}</option>
            <option value="count">{t("jobs.modeCount")}</option>
          </select>
        </div>
        {mode === "count" && (
          <div>
            <label className="label" htmlFor="req-count">{t("jobs.howMany")}</label>
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
          <label className="label" htmlFor="req-skill">{t("jobs.skill")}</label>
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
          <label className="label" htmlFor="req-level">{t("jobs.atLeastLevel")}</label>
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
          {t("jobs.addRule")}
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
                ? t("jobs.reqEveryone", { skill: nameOf(requirement.skill_id) })
                : t("jobs.reqCount", {
                    count: requirement.required_count,
                    skill: nameOf(requirement.skill_id),
                  })}{" "}
              ≥ {levelOf(requirement.min_level_id)}
              <button
                type="button"
                onClick={() => onChange(requirements.filter((_, i) => i !== index))}
                aria-label={t("jobs.removeRule")}
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
