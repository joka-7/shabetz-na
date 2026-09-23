import { useState } from "react";
import { KeyRound, LogOut, Plus, ShieldAlert, UserX } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, usePeople, useUsers } from "@/api/queries";
import { useSession } from "@/hooks/useSession";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { AdminUser, UserRole } from "@/types/api";
import { MutationError, StepShell } from "@/features/setup/steps/parts";

const ROLES: UserRole[] = ["ADMIN", "SCHEDULER", "STAFF"];

export function UsersAdmin() {
  const { t, formatDate } = useI18n();
  const { user: me } = useSession();
  const { data: users, isLoading } = useUsers();
  const { data: people } = usePeople();

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("STAFF");
  const [password, setPassword] = useState("");
  const [personId, setPersonId] = useState<number | null>(null);

  const invalidate = [keys.users] as const;
  const create = useConfigMutation(
    (payload: unknown) => api.post<AdminUser>("/api/users", payload),
    invalidate,
  );
  const update = useConfigMutation(
    ({ id, ...payload }: { id: number } & Record<string, unknown>) =>
      api.put<AdminUser>(`/api/users/${id}`, payload),
    invalidate,
  );
  const setUserPassword = useConfigMutation(
    ({ id, value }: { id: number; value: string }) =>
      api.post<AdminUser>(`/api/users/${id}/password`, { password: value }),
    invalidate,
  );
  const revoke = useConfigMutation(
    (id: number) => api.post<AdminUser>(`/api/users/${id}/revoke-sessions`, {}),
    invalidate,
  );
  const deactivate = useConfigMutation(
    (id: number) => api.del(`/api/users/${id}`),
    invalidate,
  );

  function invite(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim() || !fullName.trim()) return;
    create.mutate({
      email: email.trim(),
      full_name: fullName.trim(),
      role,
      password: password || undefined,
      person_id: personId,
    });
    setEmail("");
    setFullName("");
    setPassword("");
    setPersonId(null);
  }

  const activeAdmins = users?.filter((u) => u.role === "ADMIN" && u.is_active).length ?? 0;

  return (
    <StepShell title={t("section.users")} intro={t("users.intro")}>
      <form onSubmit={invite} className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label className="label" htmlFor="user-email">{t("login.email")}</label>
            <input
              id="user-email"
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="min-w-40 flex-1">
            <label className="label" htmlFor="user-name">{t("people.fullName")}</label>
            <input
              id="user-name"
              className="input"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="user-role">{t("users.role")}</label>
            <select
              id="user-role"
              className="input w-40"
              value={role}
              onChange={(event) => setRole(event.target.value as UserRole)}
            >
              {ROLES.map((value) => (
                <option key={value} value={value}>
                  {t(`role.${value}`)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <p className="text-xs text-slate-500">{t(`roleHint.${role}`)}</p>

        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="label" htmlFor="user-password">{t("users.initialPassword")}</label>
            <input
              id="user-password"
              className="input w-60"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {role === "STAFF" && (
            <div>
              <label className="label" htmlFor="user-person">{t("users.linkedPerson")}</label>
              <select
                id="user-person"
                className="input w-52"
                value={personId ?? ""}
                onChange={(event) =>
                  setPersonId(event.target.value ? Number(event.target.value) : null)
                }
              >
                <option value="">{t("users.notLinked")}</option>
                {people?.map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}</option>
                ))}
              </select>
            </div>
          )}
          <button className="btn-primary" type="submit" disabled={create.isPending}>
            <Plus className="h-4 w-4" aria-hidden />
            {t("users.add")}
          </button>
        </div>

        {/* Without the link a staff account has no shifts of its own to show. */}
        {role === "STAFF" && personId === null && (
          <p className="text-xs text-amber-700 dark:text-amber-400">{t("users.unlinkedWarning")}</p>
        )}
        {/* Google sign-in still needs the account to exist first, so leaving the
            password empty is a valid "invite" rather than a broken account. */}
        {!password && (
          <p className="text-xs text-slate-500">{t("users.noPasswordHint")}</p>
        )}
      </form>

      <MutationError
        error={
          create.error ?? update.error ?? setUserPassword.error ?? deactivate.error ?? revoke.error
        }
      />

      {isLoading ? (
        <Spinner />
      ) : !users?.length ? (
        <EmptyState title={t("users.empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <th className="th">{t("users.col.account")}</th>
                <th className="th">{t("users.role")}</th>
                <th className="th">{t("users.col.signIn")}</th>
                <th className="th">{t("users.col.lastSeen")}</th>
                <th className="th" />
              </tr>
            </thead>
            <tbody>
              {users.map((account) => {
                const isMe = account.id === me?.id;
                const isLastAdmin =
                  account.role === "ADMIN" && account.is_active && activeAdmins === 1;
                return (
                  <tr
                    key={account.id}
                    className={`border-b border-slate-100 dark:border-slate-800/60 ${
                      account.is_active ? "" : "opacity-50"
                    }`}
                  >
                    <td className="td">
                      <div className="font-medium">
                        {account.full_name}
                        {isMe && <span className="ms-1 text-xs text-slate-400">({t("users.you")})</span>}
                      </div>
                      <div className="text-xs text-slate-500">{account.email}</div>
                    </td>
                    <td className="td">
                      <select
                        className="input w-32 py-1 text-xs"
                        aria-label={t("users.roleFor", { email: account.email })}
                        value={account.role}
                        disabled={isLastAdmin}
                        title={
                          isLastAdmin ? t("error.lastAdmin") : undefined
                        }
                        onChange={(event) =>
                          update.mutate({
                            id: account.id,
                            role: event.target.value as UserRole,
                          })
                        }
                      >
                        {ROLES.map((value) => (
                          <option key={value} value={value}>{t(`role.${value}`)}</option>
                        ))}
                      </select>
                    </td>
                    <td className="td text-xs">
                      <div className="flex flex-wrap gap-1">
                        {account.has_password && (
                          <span className="badge bg-slate-100 dark:bg-slate-800">{t("users.password")}</span>
                        )}
                        {account.has_google && (
                          <span className="badge bg-slate-100 dark:bg-slate-800">Google</span>
                        )}
                        {!account.has_password && !account.has_google && (
                          <span className="badge bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300">
                            {t("users.cannotSignIn")}
                          </span>
                        )}
                        {account.is_locked && (
                          <span className="badge gap-1 bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300">
                            <ShieldAlert className="h-3 w-3" aria-hidden />
                            {t("users.locked")}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="td text-xs tabular-nums text-slate-500">
                      {account.last_login_at
                        ? formatDate(account.last_login_at.slice(0, 10))
                        : t("users.never")}
                    </td>
                    <td className="td">
                      <div className="flex justify-end gap-1">
                        <button
                          className="btn-ghost px-2 py-1 text-xs"
                          title={t("users.setPasswordHint")}
                          aria-label={t("users.setPasswordHint")}
                          onClick={() => {
                            const value = window.prompt(
                              t("users.newPasswordPrompt", { email: account.email }),
                            );
                            if (value) setUserPassword.mutate({ id: account.id, value });
                          }}
                        >
                          <KeyRound className="h-3.5 w-3.5" aria-hidden />
                        </button>
                        <button
                          className="btn-ghost px-2 py-1 text-xs"
                          title={t("users.signOutEverywhere")}
                          aria-label={t("users.signOutEverywhere")}
                          onClick={() => revoke.mutate(account.id)}
                        >
                          <LogOut className="h-3.5 w-3.5" aria-hidden />
                        </button>
                        {account.is_active ? (
                          <button
                            className="btn-ghost px-2 py-1 text-xs"
                            disabled={isLastAdmin}
                            title={
                              isLastAdmin ? t("users.lastAdminDeactivate") : t("users.deactivate")
                            }
                            onClick={() => deactivate.mutate(account.id)}
                          >
                            <UserX className="h-3.5 w-3.5" aria-hidden />
                          </button>
                        ) : (
                          <button
                            className="btn-ghost px-2 py-1 text-xs"
                            onClick={() =>
                              update.mutate({ id: account.id, is_active: true })
                            }
                          >
                            {t("users.reactivate")}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-slate-500">{t("users.roleChangeNote")}</p>
    </StepShell>
  );
}
