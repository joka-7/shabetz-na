import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, UserPlus } from "lucide-react";
import { api } from "@/api/client";
import { useSession } from "@/hooks/useSession";
import { ErrorNotice, LanguageSwitch, Skeleton } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import type { InvitePreview, Project } from "@/types/api";
import { LoginPage } from "@/features/auth/LoginPage";

/** The token from an invite link, if this page was opened through one. */
export function inviteTokenFromPath(path = window.location.pathname): string | null {
  const match = /^\/invite\/([A-Za-z0-9_-]{16,})\/?$/.exec(path);
  return match?.[1] ?? null;
}

/**
 * Opened from an invite link: says what it is for, has the person sign in
 * (or sign up) if they have not, and then lets them join.
 */
export function InvitePage({ token, onDone }: { token: string; onDone: () => void }) {
  const { t } = useI18n();
  const { user, refreshProjects, selectProject } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preview = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api.get<InvitePreview>(`/api/invites/${encodeURIComponent(token)}`),
    retry: false,
  });

  const invitation = preview.data && (
    <div className="mb-4 rounded-md bg-slate-50 p-3 text-sm dark:bg-slate-800/60">
      {t("invite.summary", {
        project: preview.data.project_name,
        role: t(`role.${preview.data.role}`),
      })}
    </div>
  );

  if (preview.isLoading) {
    return (
      <div className="mx-auto max-w-sm space-y-3 p-8">
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!user && preview.data) return <LoginPage needsSetup={false} banner={invitation} />;

  async function join() {
    setBusy(true);
    setError(null);
    try {
      const project = await api.post<Project>(`/api/invites/${encodeURIComponent(token)}/accept`);
      await refreshProjects();
      selectProject(project.id);
      onDone();
    } catch (err) {
      setError(errorText(err, t));
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <CalendarClock className="h-5 w-5" aria-hidden />
          <h1 className="text-lg font-semibold">{t("invite.title")}</h1>
          <LanguageSwitch className="ms-auto" />
        </div>

        {preview.isError ? (
          <>
            <ErrorNotice message={t("invite.invalid")} />
            <button className="btn-ghost mt-4 w-full justify-center" onClick={onDone}>
              {t("invite.continue")}
            </button>
          </>
        ) : (
          <>
            {invitation}
            {user && (
              <p className="mb-4 text-xs text-slate-500">
                {t("invite.signedInAs", { email: user.email })}
              </p>
            )}
            {error && <div className="mb-3"><ErrorNotice message={error} /></div>}
            <div className="flex gap-2">
              <button
                className="btn-primary flex-1 justify-center"
                disabled={busy}
                onClick={() => void join()}
              >
                <UserPlus className="h-4 w-4" aria-hidden />
                {t("invite.join")}
              </button>
              <button className="btn-ghost" onClick={onDone}>
                {t("invite.notNow")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
