import { useState } from "react";
import type { ReactNode } from "react";
import { Check, ClipboardPaste, Pencil, Trash2, X } from "lucide-react";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import { namesFrom } from "@/lib/importing";

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
  return <ul className="divide-y divide-slate-100 dark:divide-slate-700">{children}</ul>;
}

export function Row({
  children,
  onDelete,
  deleteLabel,
  onEdit,
  editLabel,
}: {
  children: ReactNode;
  onDelete?: () => void;
  deleteLabel: string;
  onEdit?: () => void;
  editLabel?: string;
}) {
  return (
    <li className="flex items-center gap-3 py-2">
      <div className="min-w-0 flex-1">{children}</div>
      {onEdit && (
        <button
          className="btn-ghost px-2 py-1"
          onClick={onEdit}
          aria-label={editLabel}
          title={editLabel}
        >
          <Pencil className="h-4 w-4" aria-hidden />
        </button>
      )}
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

/**
 * A name that turns into a text box when its pencil is pressed. Enter saves,
 * Escape cancels; an unchanged or empty name is treated as a cancel.
 */
export function EditableName({
  value,
  label,
  onSave,
  children,
}: {
  value: string;
  label: string;
  onSave: (name: string) => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  function finish(save: boolean) {
    const name = draft.trim();
    if (save && name && name !== value) onSave(name);
    setEditing(false);
  }

  if (!editing) {
    return (
      <div className="flex items-center gap-2">
        {children}
        <button
          className="btn-ghost px-1.5 py-1"
          onClick={() => {
            setDraft(value);
            setEditing(true);
          }}
          aria-label={label}
          title={label}
        >
          <Pencil className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>
    );
  }

  return (
    <form
      className="flex items-center gap-1"
      onSubmit={(event) => {
        event.preventDefault();
        finish(true);
      }}
    >
      <input
        className="input py-1"
        value={draft}
        autoFocus
        aria-label={label}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && finish(false)}
      />
      <button className="btn-ghost px-1.5 py-1" type="submit" aria-label={t("common.save")}>
        <Check className="h-4 w-4" aria-hidden />
      </button>
      <button
        className="btn-ghost px-1.5 py-1"
        type="button"
        onClick={() => finish(false)}
        aria-label={t("common.cancel")}
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </form>
  );
}

/** Surfaces a mutation failure, including the server's own explanation. */
export function MutationError({ error }: { error: unknown }) {
  const { t } = useI18n();
  if (!error) return null;
  return <ErrorNotice message={errorText(error, t)} />;
}

/**
 * Many entries at once: one per line, as pasted from a spreadsheet column or
 * typed. Entries that already exist are skipped, so pasting twice is harmless.
 */
export function PasteList({
  placeholder,
  onSubmit,
  busy,
  hint,
  toItems = namesFrom,
}: {
  placeholder: string;
  onSubmit: (items: string[]) => Promise<{ created: string[]; existing: string[] }>;
  busy: boolean;
  hint?: string;
  toItems?: (text: string) => string[];
}) {
  const { t, tn } = useI18n();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [outcome, setOutcome] = useState<string | null>(null);

  const lines = toItems(text);

  async function submit() {
    if (!lines.length) return;
    let result: { created: string[]; existing: string[] };
    try {
      result = await onSubmit(lines);
    } catch {
      return; // the step shows the failure; the text stays for another try
    }
    setText("");
    setOpen(false);
    setOutcome(
      [
        tn("paste.added", result.created.length),
        result.existing.length ? tn("paste.skipped", result.existing.length) : null,
      ]
        .filter(Boolean)
        .join(" · "),
    );
  }

  if (!open) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-ghost text-xs" onClick={() => setOpen(true)}>
          <ClipboardPaste className="h-3.5 w-3.5" aria-hidden />
          {t("paste.open")}
        </button>
        {outcome && <span className="text-xs text-emerald-700 dark:text-emerald-400">{outcome}</span>}
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <label className="label" htmlFor="paste-list">
        {t("paste.label")}
      </label>
      <textarea
        id="paste-list"
        className="input min-h-28 font-mono text-xs"
        placeholder={placeholder}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-primary" onClick={() => void submit()} disabled={busy || !lines.length}>
          {lines.length ? tn("paste.addCount", lines.length) : t("paste.addNone")}
        </button>
        <button className="btn-ghost" onClick={() => setOpen(false)}>
          {t("common.close")}
        </button>
      </div>
    </div>
  );
}

/** Weekday toggles, in the order the interface language's calendars use. */
export function WeekdayPicker({
  value,
  onChange,
  legend,
}: {
  value: number[];
  onChange: (days: number[]) => void;
  legend: string;
}) {
  const { weekdayOrder, weekdayShort } = useI18n();
  return (
    <fieldset>
      <legend className="label">{legend}</legend>
      <div className="flex flex-wrap gap-1">
        {weekdayOrder.map((day) => {
          const checked = value.includes(day);
          return (
            <label
              key={day}
              className={`btn cursor-pointer text-xs ${
                checked
                  ? "bg-indigo-600 text-white dark:bg-indigo-500"
                  : "border border-slate-300 dark:border-slate-700"
              }`}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={checked}
                onChange={() =>
                  onChange(checked ? value.filter((d) => d !== day) : [...value, day].sort((a, b) => a - b))
                }
              />
              {weekdayShort(day)}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/** The usual working week: Sunday to Thursday in Israel, Monday to Friday otherwise. */
export function useDefaultWeek(): number[] {
  const { lang } = useI18n();
  return lang === "he" ? [0, 1, 2, 3, 6] : [0, 1, 2, 3, 4];
}
