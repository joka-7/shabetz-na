import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { useI18n } from "@/i18n";
import type { MessageKey } from "@/i18n";

const SEEN_KEY = "shabetz.guideSeen";

/** Whether the first-run guide has been dismissed on this device. */
export function guideSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true; // storage unavailable: never nag
  }
}

function markSeen() {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    /* private mode: the guide simply shows again next time */
  }
}

const PAGES: { title: MessageKey; body: MessageKey; points: MessageKey[] }[] = [
  { title: "guide.1.title", body: "guide.1.body", points: ["guide.1.a", "guide.1.b", "guide.1.c"] },
  { title: "guide.2.title", body: "guide.2.body", points: ["guide.2.a", "guide.2.b", "guide.2.c"] },
  { title: "guide.3.title", body: "guide.3.body", points: ["guide.3.a", "guide.3.b", "guide.3.c"] },
  { title: "guide.4.title", body: "guide.4.body", points: ["guide.4.a", "guide.4.b", "guide.4.c"] },
];

/** A short tour of what the app does and how to use it. */
export function GuideDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [page, setPage] = useState(0);
  const last = page === PAGES.length - 1;
  const current = PAGES[page]!;

  function close() {
    markSeen();
    onClose();
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        markSeen();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 sm:items-center sm:p-4"
      onMouseDown={(event) => event.target === event.currentTarget && close()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-title"
        className="card sheet-bottom max-h-[92dvh] w-full max-w-lg space-y-4 overflow-auto rounded-b-none rounded-t-2xl p-5 shadow-2xl sm:rounded-2xl"
      >
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-semibold text-slate-500">
            {t("guide.heading")} · {page + 1}/{PAGES.length}
          </p>
          <button className="btn-ghost p-1" onClick={close} aria-label={t("common.close")}>
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div>
          <h2 id="guide-title" className="text-lg font-semibold">{t(current.title)}</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{t(current.body)}</p>
          <ul className="mt-3 list-disc space-y-1.5 ps-5 text-sm">
            {current.points.map((key) => (
              <li key={key}>{t(key)}</li>
            ))}
          </ul>
        </div>

        <div className="flex items-center justify-between gap-2">
          <button className="btn-ghost" onClick={() => setPage((p) => p - 1)} disabled={page === 0}>
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />
            {t("wizard.back")}
          </button>
          {last ? (
            <button className="btn-primary" onClick={close}>{t("guide.done")}</button>
          ) : (
            <button className="btn-primary" onClick={() => setPage((p) => p + 1)}>
              {t("wizard.next")}
              <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
