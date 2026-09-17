import { useState } from "react";
import { ChevronDown, ChevronUp, Plus } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useDivisions } from "@/api/queries";
import { DivisionBadge, EmptyState, Spinner } from "@/components/ui";
import type { Division } from "@/types/api";
import { MutationError, Row, RowList, StepShell } from "./parts";

export function DivisionsStep() {
  const { data: divisions, isLoading } = useDivisions();
  const [name, setName] = useState("");

  const create = useConfigMutation(
    (payload: { name: string; display_order: number }) =>
      api.post<Division>("/api/config/divisions", payload),
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

  function add(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    create.mutate({ name: name.trim(), display_order: divisions?.length ?? 0 });
    setName("");
  }

  /** Swapping display_order also changes the rotation, which is the point. */
  function move(index: number, delta: number) {
    if (!divisions) return;
    const current = divisions[index];
    const neighbour = divisions[index + delta];
    if (!current || !neighbour) return;
    update.mutate({ ...current, display_order: neighbour.display_order });
    update.mutate({ ...neighbour, display_order: current.display_order });
  }

  return (
    <StepShell
      title="Divisions"
      intro="Name your divisions and put them in the order duty passes between them. There is no fixed number and no preset names."
    >
      <form onSubmit={add} className="flex gap-2">
        <input
          className="input"
          placeholder="Division name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="New division name"
        />
        <button className="btn-primary shrink-0" type="submit" disabled={create.isPending}>
          <Plus className="h-4 w-4" aria-hidden />
          Add
        </button>
      </form>

      <MutationError error={create.error ?? remove.error} />

      {isLoading ? (
        <Spinner />
      ) : !divisions?.length ? (
        <EmptyState
          title="No divisions yet"
          hint="Add at least one. Duty rotates between them in the order shown here."
        />
      ) : (
        <>
          <RowList>
            {divisions.map((division, index) => (
              <Row
                key={division.id}
                deleteLabel={`Remove ${division.name}`}
                onDelete={() => remove.mutate(division.id)}
              >
                <div className="flex items-center gap-2">
                  <span className="w-6 text-xs tabular-nums text-slate-400">{index + 1}</span>
                  <DivisionBadge id={division.id} name={division.name} />
                  <div className="ml-auto flex gap-1">
                    <button
                      className="btn-ghost px-1.5 py-1"
                      onClick={() => move(index, -1)}
                      disabled={index === 0}
                      aria-label={`Move ${division.name} earlier in the rotation`}
                    >
                      <ChevronUp className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <button
                      className="btn-ghost px-1.5 py-1"
                      onClick={() => move(index, 1)}
                      disabled={index === divisions.length - 1}
                      aria-label={`Move ${division.name} later in the rotation`}
                    >
                      <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </div>
                </div>
              </Row>
            ))}
          </RowList>
          <p className="text-xs text-slate-500">
            Duty passes in this order: {divisions.map((d) => d.name).join(" → ")} → {divisions[0]?.name}
          </p>
        </>
      )}
    </StepShell>
  );
}
