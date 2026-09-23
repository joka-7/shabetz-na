import { useState } from "react";
import { Plus, Wand2 } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useLevels } from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { BulkResult } from "@/types/api";
import { MutationError, PasteList, Row, RowList, StepShell } from "./parts";

export function LadderStep() {
  const { t } = useI18n();
  const { data: levels, isLoading } = useLevels();
  const [name, setName] = useState("");

  // Offered as a starting point only; the names and depth are entirely yours.
  const suggested = t("ladder.suggested").split("|");

  // The server places new rungs above the current top, counting ranks held by
  // removed levels too, so a rank is never handed out twice.
  const add = useConfigMutation(
    (names: string[]) => api.post<BulkResult>("/api/config/proficiency-levels/bulk", { names }),
    [keys.levels],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/proficiency-levels/${id}`),
    [keys.levels],
  );

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    add.mutate([name.trim()]);
    setName("");
  }

  return (
    <StepShell title={t("section.ladder")} intro={t("ladder.intro")}>
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="input"
          placeholder={t("ladder.placeholder")}
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label={t("ladder.newLabel")}
        />
        <button className="btn-primary shrink-0" type="submit" disabled={add.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          {t("common.add")}
        </button>
      </form>

      <PasteList
        placeholder={t("ladder.pastePlaceholder")}
        hint={t("ladder.pasteHint")}
        busy={add.isPending}
        onSubmit={(names) => add.mutateAsync(names)}
      />

      <MutationError error={add.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !levels?.length ? (
        <div className="space-y-3">
          <EmptyState title={t("ladder.emptyTitle")} hint={t("ladder.emptyHint")} />
          <button
            className="btn-ghost"
            onClick={() => add.mutate(suggested)}
            disabled={add.isPending}
          >
            <Wand2 className="h-4 w-4" aria-hidden />
            {t("ladder.useSuggested", { levels: suggested.join(" · ") })}
          </button>
        </div>
      ) : (
        <RowList>
          {levels.map((level, index) => (
            <Row
              key={level.id}
              deleteLabel={t("common.removeNamed", { name: level.name })}
              onDelete={() => remove.mutate(level.id)}
            >
              <div className="flex items-center gap-3">
                <span className="w-6 text-xs tabular-nums text-slate-400">{index + 1}</span>
                <span className="font-medium">{level.name}</span>
                {index > 0 && (
                  <span className="text-xs text-slate-500">
                    {t("ladder.alsoSatisfies", { name: levels[index - 1]!.name })}
                  </span>
                )}
              </div>
            </Row>
          ))}
        </RowList>
      )}

      <p className="text-xs text-slate-500">{t("ladder.removalNote")}</p>
    </StepShell>
  );
}
