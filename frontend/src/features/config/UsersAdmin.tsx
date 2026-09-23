import { useState } from "react";
import { KeyRound, LogOut, Plus, ShieldAlert, UserX } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, usePeople, useUsers } from "@/api/queries";
import { useSession } from "@/hooks/useSession";
import { EmptyState, Spinner } from "@/components/ui";
import type { AdminUser, UserRole } from "@/types/api";
import { MutationError, StepShell } from "@/features/setup/steps/parts";

const ROLE_HINTS: Record<UserRole, string> = {
  ADMIN: "Everything, including configuration and accounts",
  SCHEDULER: "Generate schedules and review time off; cannot change configuration",
  STAFF: "See own shifts and request own time off",
};

export function UsersAdmin() {
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
    <StepShell
      title="Accounts"
      intro="Everyone who can sign in. The first-run screen creates one administrator and then closes, so accounts are added here."
    >
      <form onSubmit={invite} className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label className="label" htmlFor="user-email">Email</label>
            <input
              id="user-email"
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="min-w-40 flex-1">
            <label className="label" htmlFor="user-name">Full name</label>
            <input
              id="user-name"
              className="input"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="user-role">Role</label>
            <select
              id="user-role"
              className="input w-40"
              value={role}
              onChange={(event) => setRole(event.target.value as UserRole)}
            >
              {(Object.keys(ROLE_HINTS) as UserRole[]).map((value) => (
                <option key={value} value={value}>
                  {value.toLowerCase()}
                </option>
              ))}
            </select>
          </div>
        </div>

        <p className="text-xs text-slate-500">{ROLE_HINTS[role]}</p>

        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="label" htmlFor="user-password">Initial password (optional)</label>
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
              <label className="label" htmlFor="user-person">Linked person</label>
              <select
                id="user-person"
                className="input w-52"
                value={personId ?? ""}
                onChange={(event) =>
                  setPersonId(event.target.value ? Number(event.target.value) : null)
                }
              >
                <option value="">Not linked</option>
                {people?.map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}</option>
                ))}
              </select>
            </div>
          )}
          <button className="btn-primary" type="submit" disabled={create.isPending}>
            <Plus className="h-4 w-4" aria-hidden />
            Add account
          </button>
        </div>

        {/* Without the link a staff account has no shifts of its own to show. */}
        {role === "STAFF" && personId === null && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            A staff account not linked to a person sees an empty schedule.
          </p>
        )}
        {/* Google sign-in still needs the account to exist first, so leaving the
            password empty is a valid "invite" rather than a broken account. */}
        {!password && (
          <p className="text-xs text-slate-500">
            Leave the password empty for an account that will sign in with Google. You can
            set one later.
          </p>
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
        <EmptyState title="No accounts" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <th className="th">Account</th>
                <th className="th">Role</th>
                <th className="th">Sign-in</th>
                <th className="th">Last seen</th>
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
                        {isMe && <span className="ml-1 text-xs text-slate-400">(you)</span>}
                      </div>
                      <div className="text-xs text-slate-500">{account.email}</div>
                    </td>
                    <td className="td">
                      <select
                        className="input w-32 py-1 text-xs"
                        aria-label={`Role for ${account.email}`}
                        value={account.role}
                        disabled={isLastAdmin}
                        title={
                          isLastAdmin
                            ? "The only administrator; promote another account first"
                            : undefined
                        }
                        onChange={(event) =>
                          update.mutate({
                            id: account.id,
                            role: event.target.value as UserRole,
                          })
                        }
                      >
                        {(Object.keys(ROLE_HINTS) as UserRole[]).map((value) => (
                          <option key={value} value={value}>{value.toLowerCase()}</option>
                        ))}
                      </select>
                    </td>
                    <td className="td text-xs">
                      <div className="flex flex-wrap gap-1">
                        {account.has_password && (
                          <span className="badge bg-slate-100 dark:bg-slate-800">password</span>
                        )}
                        {account.has_google && (
                          <span className="badge bg-slate-100 dark:bg-slate-800">google</span>
                        )}
                        {!account.has_password && !account.has_google && (
                          <span className="badge bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300">
                            cannot sign in yet
                          </span>
                        )}
                        {account.is_locked && (
                          <span className="badge gap-1 bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300">
                            <ShieldAlert className="h-3 w-3" aria-hidden />
                            locked
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="td text-xs tabular-nums text-slate-500">
                      {account.last_login_at?.slice(0, 10) ?? "never"}
                    </td>
                    <td className="td">
                      <div className="flex justify-end gap-1">
                        <button
                          className="btn-ghost px-2 py-1 text-xs"
                          title="Set a new password; this also clears a lockout"
                          onClick={() => {
                            const value = window.prompt(
                              `New password for ${account.email} (at least 12 characters)`,
                            );
                            if (value) setUserPassword.mutate({ id: account.id, value });
                          }}
                        >
                          <KeyRound className="h-3.5 w-3.5" aria-hidden />
                        </button>
                        <button
                          className="btn-ghost px-2 py-1 text-xs"
                          title="Sign this account out everywhere"
                          onClick={() => revoke.mutate(account.id)}
                        >
                          <LogOut className="h-3.5 w-3.5" aria-hidden />
                        </button>
                        {account.is_active ? (
                          <button
                            className="btn-ghost px-2 py-1 text-xs"
                            disabled={isLastAdmin}
                            title={
                              isLastAdmin
                                ? "The only administrator cannot be deactivated"
                                : "Deactivate this account"
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
                            Reactivate
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

      <p className="text-xs text-slate-500">
        Changing a role or deactivating an account signs it out immediately, so the old
        rights cannot outlive the change.
      </p>
    </StepShell>
  );
}
