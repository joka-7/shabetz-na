import { useState } from "react";
import { Plus } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useSkills } from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { BulkResult } from "@/types/api";
import { MutationError, PasteList, Row, RowList, StepShell } from "./parts";

export function SkillsStep() {
  const { t } = useI18n();
  const { data: skills, isLoading } = useSkills();
  const [name, setName] = useState("");

  const add = useConfigMutation(
    (names: string[]) => api.post<BulkResult>("/api/config/skills/bulk", { names }),
    [keys.skills],
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

      <MutationError error={add.error} />

      {isLoading ? (
        <Spinner />
      ) : !skills?.length ? (
        <EmptyState title={t("skills.emptyTitle")} hint={t("skills.emptyHint")} />
      ) : (
        <RowList>
          {skills.map((skill) => (
            <Row key={skill.id} deleteLabel={t("common.removeNamed", { name: skill.name })}>
              <span className="text-sm font-medium">{skill.name}</span>
            </Row>
          ))}
        </RowList>
      )}
    </StepShell>
  );
}
