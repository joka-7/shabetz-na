import { useState } from "react";
import { Plus, Wand2 } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useLevels } from "@/api/queries";
import { EmptyState, Spinner } from "@/components/ui";
import type { ProficiencyLevel } from "@/types/api";
import { MutationError, Row, RowList, StepShell } from "./parts";

/** Offered as a starting point only; the names and depth are entirely yours. */
const SUGGESTED = ["Beginner", "Intermediate", "Expert", "Master"];

export function LadderStep() {
  const { data: levels, isLoading } = useLevels();
  const [name, setName] = useState("");

  const create = useConfigMutation(
    (payload: { name: string; rank: number }) =>
      api.post<ProficiencyLevel>("/api/config/proficiency-levels", payload),
    [keys.levels],
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/config/proficiency-levels/${id}`),
    [keys.levels],
  );

  const nextRank = levels?.length ? Math.max(...levels.map((l) => l.rank)) + 1 : 0;

  function add(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    create.mutate({ name: name.trim(), rank: nextRank });
    setName("");
  }

  function applySuggested() {
    SUGGESTED.forEach((suggestion, index) =>
      create.mutate({ name: suggestion, rank: nextRank + index }),
    );
  }

  return (
    <StepShell
      title="Proficiency ladder"
      intro="Define the rungs of skill, weakest first. Requirements are compared by position, so you can name them anything and use as many as you need."
    >
      <form onSubmit={add} className="flex gap-2">
        <input
          className="input"
          placeholder="Level name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="New level name"
        />
        <button className="btn-primary shrink-0" type="submit" disabled={create.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          Add
        </button>
      </form>

      <MutationError error={create.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !levels?.length ? (
        <div className="space-y-3">
          <EmptyState
            title="No levels yet"
            hint="Add your own, or start from a common four-rung ladder and edit it."
          />
          <button className="btn-ghost" onClick={applySuggested} disabled={create.isPending}>
            <Wand2 className="h-4 w-4" aria-hidden />
            Use {SUGGESTED.join(" · ")}
          </button>
        </div>
      ) : (
        <RowList>
          {levels.map((level) => (
            <Row
              key={level.id}
              deleteLabel={`Remove ${level.name}`}
              onDelete={() => remove.mutate(level.id)}
            >
              <div className="flex items-center gap-3">
                <span className="w-6 text-xs tabular-nums text-slate-400">{level.rank}</span>
                <span className="font-medium">{level.name}</span>
                <span className="text-xs text-slate-500">
                  satisfies requirements up to {level.name.toLowerCase()}
                </span>
              </div>
            </Row>
          ))}
        </RowList>
      )}

      <p className="text-xs text-slate-500">
        A level still used by a person or a job requirement cannot be removed; the server
        names what refers to it.
      </p>
    </StepShell>
  );
}
