import type { ReactNode } from "react";
import { Trash2 } from "lucide-react";
import { ApiError } from "@/api/client";
import { ErrorNotice } from "@/components/ui";

export function StepShell({
  title,
  intro,
  children,
}: {
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-medium">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{intro}</p>
      </div>
      {children}
    </section>
  );
}

export function RowList({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-slate-100 dark:divide-slate-800">{children}</ul>;
}

export function Row({
  children,
  onDelete,
  deleteLabel,
}: {
  children: ReactNode;
  onDelete?: () => void;
  deleteLabel: string;
}) {
  return (
    <li className="flex items-center gap-3 py-2">
      <div className="min-w-0 flex-1">{children}</div>
      {onDelete && (
        <button
          className="btn-ghost px-2 py-1"
          onClick={onDelete}
          aria-label={deleteLabel}
          title={deleteLabel}
        >
          <Trash2 className="h-4 w-4" aria-hidden />
        </button>
      )}
    </li>
  );
}

/** Surfaces a mutation failure, including the server's own explanation. */
export function MutationError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <ErrorNotice
      message={error instanceof ApiError ? error.message : "The change could not be saved"}
    />
  );
}
