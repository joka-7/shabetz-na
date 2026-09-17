import { useState } from "react";
import {
  CalendarClock,
  CalendarDays,
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
import { Skeleton } from "@/components/ui";

type Tab = "dashboard" | "config" | "timeoff";

export function App() {
  const { user, capabilities, loading, signOut, refresh } = useSession();
  const [tab, setTab] = useState<Tab>("dashboard");
  const [wizardDone, setWizardDone] = useState(false);

  if (loading || !capabilities) {
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

  if (!user) return <LoginPage needsSetup={false} />;

  // A fresh administrator lands in the wizard rather than an empty dashboard.
  if (can.editConfig(user) && !wizardDone) {
    return (
      <SetupWizard
        onFinished={() => {
          setWizardDone(true);
          void refresh();
        }}
      />
    );
  }

  const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard; show: boolean }[] = [
    { id: "dashboard", label: "Schedule", icon: LayoutDashboard, show: true },
    { id: "timeoff", label: "Time off", icon: CalendarDays, show: true },
    { id: "config", label: "Configuration", icon: Settings2, show: can.editConfig(user) },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold">
            <CalendarClock className="h-5 w-5" aria-hidden />
            Shabetz
          </div>

          <nav className="flex gap-1" aria-label="Sections">
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

          <div className="ml-auto flex items-center gap-3 text-sm">
            {can.editConfig(user) && (
              <button className="btn-ghost text-xs" onClick={() => setWizardDone(false)}>
                <Wand2 className="h-3.5 w-3.5" aria-hidden />
                Setup
              </button>
            )}
            <span className="hidden text-slate-500 sm:inline">
              {user.full_name} · {user.role.toLowerCase()}
            </span>
            <button className="btn-ghost" onClick={() => void signOut()}>
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl p-4">
        {tab === "dashboard" && <DashboardView />}
        {tab === "timeoff" && <TimeOffView />}
        {tab === "config" && can.editConfig(user) && <ConfigView />}
      </main>
    </div>
  );
}
