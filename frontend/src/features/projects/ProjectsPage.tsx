import { useState } from "react";
import { CalendarClock, ChevronRight, FolderPlus, LogOut } from "lucide-react";
import { api } from "@/api/client";
import { useSession } from "@/hooks/useSession";
import { EmptyState, ErrorNotice, LanguageSwitch } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";

/**
 * Where a signed-in account chooses what to work on: its projects, each with
 * its role there, and a new one of its own.
 */
export function ProjectsPage() {
  const { t } = useI18n();
  const { user, projects, selectProject, createProject, refreshProjects, signOut, capabilities } =
    useSession();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The desktop app is one organisation; it makes its project at setup.
  const canCreate = capabilities?.deployment !== "desktop" || projects.length === 0;

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createProject(name.trim());
    } catch (err) {
      setError(errorText(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function leave(id: number, projectName: string) {
    if (!window.confirm(t("projects.leaveConfirm", { name: projectName }))) return;
    setError(null);
    try {
      await api.post("/api/project/leave", undefined, { "x-project-id": String(id) });
      await refreshProjects();
    } catch (err) {
      setError(errorText(err, t));
    }
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold">
            <CalendarClock className="h-5 w-5" aria-hidden />
            Shabetz
          </div>
          <div className="ms-auto flex items-center gap-3 text-sm">
            <LanguageSwitch />
            <span className="hidden text-slate-500 sm:inline">{user?.full_name}</span>
            <button className="btn-ghost" onClick={() => void signOut()}>
              <LogOut className="h-4 w-4 rtl:rotate-180" aria-hidden />
              {t("nav.signOut")}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-4 p-4">
        <section className="card">
          <h1 className="mb-1 text-lg font-semibold">{t("projects.title")}</h1>
          <p className="mb-4 text-sm text-slate-500">{t("projects.intro")}</p>

          {projects.length === 0 ? (
            <EmptyState title={t("projects.empty")} hint={t("projects.emptyHint")} />
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {projects.map((project) => (
                <li key={project.id} className="flex items-center gap-2 py-1">
                  <button
                    className="flex flex-1 items-center gap-3 rounded-md px-2 py-2 text-start hover:bg-slate-50 dark:hover:bg-slate-800"
                    onClick={() => selectProject(project.id)}
                  >
                    <span className="flex-1 font-medium">{project.name}</span>
                    <span className="badge bg-slate-100 dark:bg-slate-800">
                      {t(`role.${project.role}`)}
                    </span>
                    <ChevronRight className="h-4 w-4 text-slate-400 rtl:rotate-180" aria-hidden />
                  </button>
                  {capabilities?.deployment !== "desktop" && (
                    <button
                      className="btn-ghost px-2 py-1 text-xs"
                      onClick={() => void leave(project.id, project.name)}
                    >
                      {t("projects.leave")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {canCreate && (
          <section className="card">
            <h2 className="label">{t("projects.new")}</h2>
            <form onSubmit={create} className="flex flex-wrap items-end gap-2">
              <input
                className="input min-w-52 flex-1"
                aria-label={t("projects.name")}
                placeholder={t("projects.namePlaceholder")}
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <button className="btn-primary" type="submit" disabled={busy || !name.trim()}>
                <FolderPlus className="h-4 w-4" aria-hidden />
                {t("projects.create")}
              </button>
            </form>
            <p className="mt-2 text-xs text-slate-500">{t("projects.createHint")}</p>
          </section>
        )}

        {error && <ErrorNotice message={error} />}
      </main>
    </div>
  );
}
