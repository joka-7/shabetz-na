import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Languages, Loader2, XCircle } from "lucide-react";
import { useI18n } from "@/i18n";
import type { FeasibilityVerdict, WarningSeverity } from "@/types/api";

export function Spinner({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label ?? t("common.loading")}
    </div>
  );
}

/** Switches to the other language; labelled in the language it switches to. */
export function LanguageSwitch({ className = "" }: { className?: string }) {
  const { lang, setLang } = useI18n();
  const next = lang === "he" ? "en" : "he";
  return (
    <button
      className={`btn-ghost text-xs ${className}`}
      onClick={() => setLang(next)}
      lang={next}
      title={next === "he" ? "החלפה לעברית" : "Switch to English"}
    >
      <Languages className="h-3.5 w-3.5" aria-hidden />
      {next === "he" ? "עברית" : "English"}
    </button>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-200 dark:bg-slate-800 ${className}`} />;
}

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "warn" | "danger";
}) {
  const toneClass =
    tone === "danger"
      ? "text-rose-600 dark:text-rose-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : "text-slate-900 dark:text-slate-100";
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

/**
 * Colour is paired with a distinct icon and text so the meaning survives for
 * viewers who cannot distinguish the hues.
 */
export function VerdictBadge({ verdict }: { verdict: FeasibilityVerdict }) {
  const { t } = useI18n();
  const config = {
    OK: { icon: CheckCircle2, cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300", text: t("verdict.ok") },
    TIGHT: { icon: AlertTriangle, cls: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300", text: t("verdict.tight") },
    INFEASIBLE: { icon: XCircle, cls: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300", text: t("verdict.infeasible") },
  }[verdict];
  const Icon = config.icon;
  return (
    <span className={`badge gap-1 ${config.cls}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {config.text}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: WarningSeverity }) {
  const { t } = useI18n();
  const config = {
    ERROR: { icon: XCircle, cls: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300" },
    WARNING: { icon: AlertTriangle, cls: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300" },
    INFO: { icon: Info, cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  }[severity];
  const Icon = config.icon;
  return (
    <span className={`badge gap-1 ${config.cls}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {t(`severity.${severity}`)}
    </span>
  );
}

const DIVISION_TONES = [
  "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-300",
  "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-300",
  "bg-teal-100 text-teal-900 dark:bg-teal-950 dark:text-teal-300",
  "bg-orange-100 text-orange-900 dark:bg-orange-950 dark:text-orange-300",
  "bg-fuchsia-100 text-fuchsia-900 dark:bg-fuchsia-950 dark:text-fuchsia-300",
  "bg-lime-100 text-lime-900 dark:bg-lime-950 dark:text-lime-300",
];

/** Divisions are user-created, so colours are derived rather than hardcoded. */
export function DivisionBadge({ id, name }: { id: number; name: string }) {
  return <span className={`badge ${DIVISION_TONES[id % DIVISION_TONES.length]}`}>{name}</span>;
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
      {message}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center dark:border-slate-700">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}
