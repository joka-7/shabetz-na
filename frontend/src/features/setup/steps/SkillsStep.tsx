import { useState } from "react";
import { Plus } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useSkills } from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import type { Skill } from "@/types/api";
import { MutationError, Row, RowList, StepShell } from "./parts";

export function SkillsStep() {
  const { data: skills, isLoading } = useSkills();
  const [name, setName] = useState("");

  const create = useConfigMutation(
    (payload: { name: string }) => api.post<Skill>("/api/config/skills", payload),
    [keys.skills],
  );

  function add(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    create.mutate({ name: name.trim() });
    setName("");
  }

  return (
    <StepShell
      title="Skills"
      intro="List the competencies your jobs require. Leadership roles are just skills too — you decide which ones a job demands, and how many people need them."
    >
      <form onSubmit={add} className="flex gap-2">
        <input
          className="input"
          placeholder="e.g. Cleaning, Coding, Team Leader"
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="New skill name"
        />
        <button className="btn-primary shrink-0" type="submit" disabled={create.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          Add
        </button>
      </form>

      <MutationError error={create.error} />

      {isLoading ? (
        <Spinner />
      ) : !skills?.length ? (
        <EmptyState
          title="No skills yet"
          hint="Add the competencies you will reference when defining jobs."
        />
      ) : (
        <RowList>
          {skills.map((skill) => (
            <Row key={skill.id} deleteLabel={`Remove ${skill.name}`}>
              <span className="text-sm font-medium">{skill.name}</span>
            </Row>
          ))}
        </RowList>
      )}
    </StepShell>
  );
}
