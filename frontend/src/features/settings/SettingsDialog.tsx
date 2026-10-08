import { useEffect } from "react";
import { BookOpen, FolderGit2, Github, Globe, Mail, MessageSquare, X } from "lucide-react";
import { LanguageSwitch } from "@/components/ui";
import { useI18n } from "@/i18n";
import { useSession } from "@/hooks/useSession";
import { GetTheApp } from "./GetTheApp";

/** Language switcher and the project's credit links, out of the header/footer and into one place. */
export function SettingsDialog({
  onClose,
  onOpenGuide,
}: {
  onClose: () => void;
  onOpenGuide: () => void;
}) {
  const { t } = useI18n();
  const { capabilities } = useSession();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 sm:items-center sm:p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="card sheet-bottom max-h-[92dvh] w-full max-w-md space-y-4 overflow-auto rounded-b-none rounded-t-2xl p-5 shadow-2xl sm:rounded-2xl"
      >
        <div className="flex items-start justify-between gap-2">
          <h2 id="settings-title" className="text-base font-semibold">{t("settings.heading")}</h2>
          <button className="btn-ghost p-1" onClick={onClose} aria-label={t("common.close")}>
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-slate-500">{t("settings.languageHeading")}</h3>
          <LanguageSwitch />
        </div>

        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-slate-500">{t("settings.helpHeading")}</h3>
          <button
            className="btn-ghost"
            onClick={() => {
              onClose();
              onOpenGuide();
            }}
          >
            <BookOpen className="h-4 w-4" aria-hidden />
            {t("settings.showGuide")}
          </button>
        </div>

        {/* The desktop app is already installed; this is for the website. */}
        {capabilities?.deployment !== "desktop" && (
          <div>
            <h3 className="mb-1.5 text-xs font-semibold text-slate-500">{t("getapp.heading")}</h3>
            <GetTheApp />
          </div>
        )}

        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-slate-500">{t("settings.linksHeading")}</h3>
          <div className="flex flex-wrap items-center justify-center gap-1">
            <a href="https://github.com/joka-7" target="_blank" rel="noreferrer" aria-label="GitHub" title="GitHub" className="tap-fx hover:text-slate-600 dark:hover:text-slate-300 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 active:bg-slate-200 dark:active:bg-slate-700 active:scale-90 transition-all inline-flex flex-col items-center justify-center gap-0.5">
              <Github className="h-4 w-4" aria-hidden />
              <span className="text-[9px] leading-none">GitHub</span>
            </a>
            <a href="https://jk-dev-7.vercel.app" target="_blank" rel="noreferrer" aria-label="jk.dev portfolio" title="jk.dev portfolio" className="tap-fx hover:text-slate-600 dark:hover:text-slate-300 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 active:bg-slate-200 dark:active:bg-slate-700 active:scale-90 transition-all inline-flex flex-col items-center justify-center gap-0.5">
              <Globe className="h-4 w-4" aria-hidden />
              <span className="text-[9px] leading-none">Site</span>
            </a>
            <a href="https://github.com/joka-7/shabetz-na" target="_blank" rel="noreferrer" aria-label="View repository" title="View repository" className="tap-fx hover:text-slate-600 dark:hover:text-slate-300 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 active:bg-slate-200 dark:active:bg-slate-700 active:scale-90 transition-all inline-flex flex-col items-center justify-center gap-0.5">
              <FolderGit2 className="h-4 w-4" aria-hidden />
              <span className="text-[9px] leading-none">Code</span>
            </a>
            <a href="mailto:joka.dev.7@gmail.com" rel="noreferrer" aria-label="Send feedback by email" title="Send feedback by email" className="tap-fx hover:text-slate-600 dark:hover:text-slate-300 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 active:bg-slate-200 dark:active:bg-slate-700 active:scale-90 transition-all inline-flex flex-col items-center justify-center gap-0.5">
              <Mail className="h-4 w-4" aria-hidden />
              <span className="text-[9px] leading-none">Email</span>
            </a>
            <a href="https://github.com/joka-7/shabetz-na/issues/new" target="_blank" rel="noreferrer" aria-label="Report an issue" title="Report an issue" className="tap-fx hover:text-slate-600 dark:hover:text-slate-300 p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 active:bg-slate-200 dark:active:bg-slate-700 active:scale-90 transition-all inline-flex flex-col items-center justify-center gap-0.5">
              <MessageSquare className="h-4 w-4" aria-hidden />
              <span className="text-[9px] leading-none">Feedback</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
