import { useState } from "react";
import { ChevronDown, ChevronUp, Plus } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useDivisions } from "@/api/queries";
import { DivisionBadge, EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { BulkResult, Division } from "@/types/api";
import { MutationError, PasteList, Row, RowList, StepShell } from "./parts";

export function DivisionsStep() {
  const { t, dir } = useI18n();
  const { data: divisions, isLoading } = useDivisions();
  const [name, setName] = useState("");

  // Adding goes through the bulk route even for one name: it appends to the
  // end of the rotation and brings back a removed division of the same name.
  const add = useConfigMutation(
    (names: string[]) => api.post<BulkResult>("/api/config/divisions/bulk", { names }),
    [keys.divisions],
  );
  const update = useConfigMutation(
    ({ id, ...payload }: Division) => api.put<Division>(`/api/config/divisions/${id}`, payload),
    [keys.divisions],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/divisions/${id}`),
    [keys.divisions, keys.people],
  );

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    add.mutate([name.trim()]);
    setName("");
  }

  /**
   * Reordering also changes the rotation, which is the point. Every division
   * is renumbered by position, since stored orders need not be consecutive.
   */
  function move(index: number, delta: number) {
    if (!divisions || !divisions[index + delta]) return;
    const reordered = [...divisions];
    const [moved] = reordered.splice(index, 1);
    reordered.splice(index + delta, 0, moved!);
    reordered.forEach((division, position) => {
      if (division.display_order !== position) {
        update.mutate({ ...division, display_order: position });
      }
    });
  }

  return (
    <StepShell title={t("section.divisions")} intro={t("divisions.intro")}>
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="input"
          placeholder={t("divisions.placeholder")}
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label={t("divisions.newLabel")}
        />
        <button className="btn-primary shrink-0" type="submit" disabled={add.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          {t("common.add")}
        </button>
      </form>

      <PasteList
        placeholder={t("divisions.pastePlaceholder")}
        busy={add.isPending}
        onSubmit={(names) => add.mutateAsync(names)}
      />

      <MutationError error={add.error ?? update.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !divisions?.length ? (
        <EmptyState title={t("divisions.emptyTitle")} hint={t("divisions.emptyHint")} />
      ) : (
        <>
          <RowList>
            {divisions.map((division, index) => (
              <Row
                key={division.id}
                deleteLabel={t("common.removeNamed", { name: division.name })}
                onDelete={() => remove.mutate(division.id)}
              >
                <div className="flex items-center gap-2">
                  <span className="w-6 text-xs tabular-nums text-slate-400">{index + 1}</span>
                  <DivisionBadge id={division.id} name={division.name} />
                  <div className="ms-auto flex gap-1">
                    <button
                      className="btn-ghost px-1.5 py-1"
                      onClick={() => move(index, -1)}
                      disabled={index === 0 || update.isPending}
                      aria-label={t("divisions.moveEarlier", { name: division.name })}
                    >
                      <ChevronUp className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <button
                      className="btn-ghost px-1.5 py-1"
                      onClick={() => move(index, 1)}
                      disabled={index === divisions.length - 1 || update.isPending}
                      aria-label={t("divisions.moveLater", { name: division.name })}
                    >
                      <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </div>
                </div>
              </Row>
            ))}
          </RowList>
          <p className="text-xs text-slate-500">
            {t("divisions.order", {
              order: [...divisions.map((d) => d.name), divisions[0]!.name].join(dir === "rtl" ? " ← " : " → "),
            })}
          </p>
        </>
      )}
    </StepShell>
  );
}
