import { useState } from "react";
import type { ReactNode } from "react";
import { ClipboardPaste, Trash2 } from "lucide-react";
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
    <div className="space-y-2 rounded-md border border-slate-200 p-3 dark:border-slate-800">
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
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
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
