import { useState } from "react";
import { Plus } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useSkills } from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { BulkResult, Skill } from "@/types/api";
import { EditableName, MutationError, PasteList, Row, RowList, StepShell } from "./parts";

export function SkillsStep() {
  const { t } = useI18n();
  const { data: skills, isLoading } = useSkills();
  const [name, setName] = useState("");

  const add = useConfigMutation(
    (names: string[]) => api.post<BulkResult>("/api/config/skills/bulk", { names }),
    [keys.skills],
  );

  const update = useConfigMutation(
    ({ id, ...payload }: Skill) => api.put<Skill>(`/api/config/skills/${id}`, payload),
    [keys.skills, keys.jobs, keys.people],
  );

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    add.mutate([name.trim()]);
    setName("");
  }

  return (
    <StepShell title={t("section.skills")} intro={t("skills.intro")}>
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="input"
          placeholder={t("skills.placeholder")}
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label={t("skills.newLabel")}
        />
        <button className="btn-primary shrink-0" type="submit" disabled={add.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          {t("common.add")}
        </button>
      </form>

      <PasteList
        placeholder={t("skills.pastePlaceholder")}
        busy={add.isPending}
        onSubmit={(names) => add.mutateAsync(names)}
      />

      <MutationError error={add.error ?? update.error} />

      {isLoading ? (
        <Spinner />
      ) : !skills?.length ? (
        <EmptyState title={t("skills.emptyTitle")} hint={t("skills.emptyHint")} />
      ) : (
        <RowList>
          {skills.map((skill) => (
            <Row key={skill.id} deleteLabel={t("common.removeNamed", { name: skill.name })}>
              <EditableName
                value={skill.name}
                label={t("common.editNamed", { name: skill.name })}
                onSave={(name) => update.mutate({ ...skill, name })}
              >
                <span className="text-sm font-medium">{skill.name}</span>
              </EditableName>
            </Row>
          ))}
        </RowList>
      )}
    </StepShell>
  );
}
