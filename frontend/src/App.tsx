import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  FolderOpen,
  LayoutDashboard,
  Repeat,
  LogOut,
  Settings as SettingsIcon,
  Settings2,
  Wand2,
} from "lucide-react";
import { can, useSession } from "@/hooks/useSession";
import { LoginPage } from "@/features/auth/LoginPage";
import { SetupWizard } from "@/features/setup/SetupWizard";
import { ConfigView } from "@/features/config/ConfigView";
import { DashboardView } from "@/features/dashboard/DashboardView";
import { GuideDialog, guideSeen } from "@/features/guide/GuideDialog";
import { SettingsDialog } from "@/features/settings/SettingsDialog";
import { SwapsView } from "@/features/swaps/SwapsView";
import { TimeOffView } from "@/features/timeoff/TimeOffView";
import { InvitePage, inviteTokenFromPath } from "@/features/projects/InvitePage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { Logo } from "@/components/Logo";
import { Skeleton } from "@/components/ui";
import { useI18n } from "@/i18n";
import { api } from "@/api/client";
import { keys } from "@/api/queries";
import type { Settings } from "@/types/api";

type Tab = "dashboard" | "config" | "timeoff" | "swaps";

/** Free hosting sleeps when idle; say so instead of leaving a blank skeleton. */
function WakeNotice() {
  const { t } = useI18n();
  const [show, setShow] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setShow(true), 4000);
    return () => clearTimeout(id);
  }, []);
  if (!show) return null;
  return (
    <p role="status" className="text-sm text-slate-500 dark:text-slate-400">
      {t("common.waking")}
    </p>
  );
}

export function App() {
  const { user, capabilities, loading, signOut, refreshProjects, project, projects, selectProject } =
    useSession();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("dashboard");
  const [inviteToken, setInviteToken] = useState(() => inviteTokenFromPath());
  // Reopened on request from the header; whether it shows by default comes
  // from the server, so finishing it once is remembered across reloads.
  const [wizardReopened, setWizardReopened] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  // Opens by itself on a first-time setup, and on request from Settings.
  const [showGuide, setShowGuide] = useState(false);

  const editor = can.editConfig(project);
  const settings = useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<Settings>("/api/config/settings"),
    enabled: editor,
  });

  const firstSetup = editor && settings.data?.setup_completed === false;
  useEffect(() => {
    if (firstSetup && !guideSeen()) setShowGuide(true);
  }, [firstSetup]);

  // The sign-in page does not wait for the server (it may be asleep); only a
  // signed-in session needs the server's answers before anything can show.
  if (loading || (user && !capabilities) || (editor && settings.isLoading)) {
    return (
      <div className="mx-auto max-w-5xl space-y-3 p-8">
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-32 w-full" />
        <WakeNotice />
      </div>
    );
  }

  // No account exists yet: the only thing anyone can do is create the first
  // administrator, and that route closes permanently once they have.
  if (capabilities && !capabilities.setup_complete) {
    return <LoginPage needsSetup />;
  }

  if (inviteToken) {
    return (
      <InvitePage
        token={inviteToken}
        onDone={() => {
          window.history.replaceState(null, "", "/");
          setInviteToken(null);
        }}
      />
    );
  }

  if (!user) return <LoginPage needsSetup={false} />;
  if (!capabilities) return null; // unreachable: handled by the loading state above

  if (!project) return <ProjectsPage />;

  // A fresh project opens in the wizard rather than an empty dashboard.
  if (editor && (wizardReopened || settings.data?.setup_completed === false)) {
    return (
      <>
      {showGuide && <GuideDialog onClose={() => setShowGuide(false)} />}
      <SetupWizard
        firstRun={settings.data?.setup_completed === false}
        onShowGuide={() => setShowGuide(true)}
        onFinished={async () => {
          await api.post("/api/setup/complete");
          await queryClient.invalidateQueries({ queryKey: keys.settings });
          setWizardReopened(false);
          // The wizard may have renamed the project.
          void refreshProjects();
        }}
      />
      </>
    );
  }

  const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard; show: boolean }[] = [
    { id: "dashboard", label: editor ? t("nav.schedule") : t("nav.myShifts"), icon: LayoutDashboard, show: true },
    { id: "timeoff", label: t("nav.timeOff"), icon: CalendarDays, show: true },
    { id: "swaps", label: t("nav.swaps"), icon: Repeat, show: true },
    { id: "config", label: t("nav.configuration"), icon: Settings2, show: editor },
  ];

  return (
    <div className="min-h-screen">
      <header className="safe-top border-b border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800 print:hidden">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <div className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <Logo />
            Shabetz
          </div>

          {/* One organisation on the desktop; on the website, any number. */}
          {capabilities.deployment !== "desktop" && (
            <div className="flex items-center gap-1">
              <select
                className="input w-auto max-w-56 py-1 text-sm"
                aria-label={t("projects.switch")}
                value={project.id}
                onChange={(event) => {
                  setTab("dashboard");
                  selectProject(Number(event.target.value));
                }}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <button
                className="btn-ghost px-2 py-1"
                title={t("projects.all")}
                aria-label={t("projects.all")}
                onClick={() => selectProject(null)}
              >
                <FolderOpen className="h-4 w-4" aria-hidden />
              </button>
            </div>
          )}

          {/* A tab strip on large screens; a bottom bar on phones, where thumbs reach. */}
          <nav
            className="safe-bottom fixed inset-x-0 bottom-0 z-40 flex justify-around gap-1 border-t border-slate-200 bg-white px-2 pt-2 dark:border-slate-700 dark:bg-slate-800 sm:static sm:justify-start sm:rounded-xl sm:border sm:bg-slate-100 sm:p-1 sm:dark:bg-slate-900 print:hidden"
            aria-label={t("nav.sections")}
          >
            {tabs.filter((t) => t.show).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                aria-current={tab === id ? "page" : undefined}
                className={`min-h-11 min-w-0 flex-1 flex-col justify-center gap-0.5 px-1 text-[11px] sm:min-h-0 sm:flex-none sm:flex-row sm:gap-2 sm:px-3 sm:text-sm ${
                  tab === id ? "pill-active" : "pill"
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </button>
            ))}
          </nav>

          <div className="ms-auto flex items-center gap-3 text-sm">
            <button
              className="btn-ghost p-1"
              onClick={() => setShowSettings(true)}
              aria-label={t("nav.settings")}
              title={t("nav.settings")}
            >
              <SettingsIcon className="h-4 w-4" aria-hidden />
            </button>
            {editor && (
              <button className="btn-ghost text-xs" onClick={() => setWizardReopened(true)}>
                <Wand2 className="h-3.5 w-3.5" aria-hidden />
                {t("nav.setup")}
              </button>
            )}
            <span className="hidden text-slate-500 sm:inline">
              {user.full_name} · {t(`role.${project.role}`)}
            </span>
            <button className="btn-ghost" onClick={() => void signOut()}>
              <LogOut className="h-4 w-4 rtl:rotate-180" aria-hidden />
              {t("nav.signOut")}
            </button>
          </div>
        </div>
      </header>

      {/* Keyed on the project so nothing typed in one shows up in another. */}
      <main key={project.id} className="mx-auto max-w-7xl p-4 pb-28 sm:pb-4">
        {tab === "dashboard" && <DashboardView />}
        {tab === "timeoff" && <TimeOffView />}
        {tab === "swaps" && <SwapsView />}
        {tab === "config" && editor && <ConfigView />}
      </main>

      <footer className="mx-auto flex max-w-7xl flex-col print:hidden items-center gap-1.5 px-4 py-4 pb-24 sm:pb-4 text-slate-400">
        <span className="text-xs">{t("footer.credit")}</span>
      </footer>

      {showSettings && (
        <SettingsDialog onClose={() => setShowSettings(false)} onOpenGuide={() => setShowGuide(true)} />
      )}
      {showGuide && <GuideDialog onClose={() => setShowGuide(false)} />}
    </div>
  );
}
