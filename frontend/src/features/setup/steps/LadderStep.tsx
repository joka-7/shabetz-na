import { useState } from "react";
import { Plus, Wand2 } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useLevels } from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { BulkResult, ProficiencyLevel } from "@/types/api";
import { EditableName, MutationError, PasteList, Row, RowList, StepShell } from "./parts";
import { useEnsureYesNo } from "./yesNo";

export function LadderStep() {
  const { t } = useI18n();
  const { data: levels, isLoading } = useLevels();
  const [name, setName] = useState("");
  const [wantLevels, setWantLevels] = useState(false);
  const ensureYesNo = useEnsureYesNo();

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

  const update = useConfigMutation(
    ({ id, ...payload }: ProficiencyLevel) =>
      api.put<ProficiencyLevel>(`/api/config/proficiency-levels/${id}`, payload),
    [keys.levels, keys.jobs, keys.people],
  );

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    add.mutate([name.trim()]);
    setName("");
  }

  const count = levels?.length ?? 0;
  const withLevels = count > 1 || wantLevels;

  const choice = (active: boolean, disabled: boolean, onClick: () => void, title: string, hint: string) => (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      disabled={disabled}
      onClick={onClick}
      className={`flex-1 rounded-lg border p-3 text-start disabled:opacity-50 ${
        active
          ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950"
          : "border-slate-200 hover:border-slate-300 dark:border-slate-700"
      }`}
    >
      <span className="block text-sm font-semibold">{title}</span>
      <span className="block text-xs text-slate-500">{hint}</span>
    </button>
  );

  return (
    <StepShell title={t("section.ladder")} intro={t("ladder.intro")}>
      <div role="radiogroup" aria-label={t("ladder.modeHeading")} className="flex flex-col gap-2 sm:flex-row">
        {choice(
          !withLevels,
          count > 1,
          () => {
            setWantLevels(false);
            void ensureYesNo();
          },
          t("ladder.modeYesNo"),
          count > 1 ? t("ladder.modeNeedRemove") : t("ladder.modeYesNoHint"),
        )}
        {choice(withLevels, false, () => setWantLevels(true), t("ladder.modeLevels"), t("ladder.modeLevelsHint"))}
      </div>

      {!withLevels ? (
        <p className="text-sm text-slate-500">{t("ladder.simpleNote")}</p>
      ) : (
      <>
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

      <MutationError error={add.error ?? remove.error ?? update.error} />

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
                <EditableName
                  value={level.name}
                  label={t("common.editNamed", { name: level.name })}
                  onSave={(name) => update.mutate({ ...level, name })}
                >
                  <span className="font-medium">{level.name}</span>
                </EditableName>
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
      </>
      )}
    </StepShell>
  );
}
