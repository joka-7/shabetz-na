import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  CalendarDays,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  Settings2,
  Wand2,
} from "lucide-react";
import { can, useSession } from "@/hooks/useSession";
import { LoginPage } from "@/features/auth/LoginPage";
import { SetupWizard } from "@/features/setup/SetupWizard";
import { ConfigView } from "@/features/config/ConfigView";
import { DashboardView } from "@/features/dashboard/DashboardView";
import { TimeOffView } from "@/features/timeoff/TimeOffView";
import { InvitePage, inviteTokenFromPath } from "@/features/projects/InvitePage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { LanguageSwitch, Skeleton } from "@/components/ui";
import { useI18n } from "@/i18n";
import { api } from "@/api/client";
import { keys } from "@/api/queries";
import type { Settings } from "@/types/api";

type Tab = "dashboard" | "config" | "timeoff";

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

  const editor = can.editConfig(project);
  const settings = useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<Settings>("/api/config/settings"),
    enabled: editor,
  });

  if (loading || !capabilities || (editor && settings.isLoading)) {
    return (
      <div className="mx-auto max-w-5xl space-y-3 p-8">
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  // No account exists yet: the only thing anyone can do is create the first
  // administrator, and that route closes permanently once they have.
  if (!capabilities.setup_complete) {
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

  if (!project) return <ProjectsPage />;

  // A fresh project opens in the wizard rather than an empty dashboard.
  if (editor && (wizardReopened || settings.data?.setup_completed === false)) {
    return (
      <SetupWizard
        firstRun={settings.data?.setup_completed === false}
        onFinished={async () => {
          await api.post("/api/setup/complete");
          await queryClient.invalidateQueries({ queryKey: keys.settings });
          setWizardReopened(false);
          // The wizard may have renamed the project.
          void refreshProjects();
        }}
      />
    );
  }

  const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard; show: boolean }[] = [
    { id: "dashboard", label: t("nav.schedule"), icon: LayoutDashboard, show: true },
    { id: "timeoff", label: t("nav.timeOff"), icon: CalendarDays, show: true },
    { id: "config", label: t("nav.configuration"), icon: Settings2, show: editor },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold">
            <CalendarClock className="h-5 w-5" aria-hidden />
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

          <nav className="flex gap-1" aria-label={t("nav.sections")}>
            {tabs.filter((t) => t.show).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                aria-current={tab === id ? "page" : undefined}
                className={`btn text-sm ${
                  tab === id
                    ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                    : "hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </button>
            ))}
          </nav>

          <div className="ms-auto flex items-center gap-3 text-sm">
            <LanguageSwitch />
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
      <main key={project.id} className="mx-auto max-w-7xl p-4">
        {tab === "dashboard" && <DashboardView />}
        {tab === "timeoff" && <TimeOffView />}
        {tab === "config" && editor && <ConfigView />}
      </main>
    </div>
  );
}
