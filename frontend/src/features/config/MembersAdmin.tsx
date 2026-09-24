import { useState } from "react";
import { Check, Copy, KeyRound, Link2, Plus, ShieldAlert, Trash2, UserMinus } from "lucide-react";
import { api } from "@/api/client";
import { keys, useConfigMutation, useInvites, useMembers, usePeople } from "@/api/queries";
import { useSession } from "@/hooks/useSession";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { InviteCreated, Member, Project, ProjectRole } from "@/types/api";
import { MutationError, StepShell } from "@/features/setup/steps/parts";

const ROLES: ProjectRole[] = ["ADMIN", "COLLABORATOR", "STAFF"];

function RoleSelect({
  id,
  value,
  onChange,
  disabled,
  label,
  title,
}: {
  id?: string;
  value: ProjectRole;
  onChange: (role: ProjectRole) => void;
  disabled?: boolean;
  label?: string;
  title?: string;
}) {
  const { t } = useI18n();
  return (
    <select
      id={id}
      className="input w-40"
      aria-label={label}
      title={title}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value as ProjectRole)}
    >
      {ROLES.map((role) => (
        <option key={role} value={role}>{t(`role.${role}`)}</option>
      ))}
    </select>
  );
}

function PersonSelect({
  id,
  value,
  onChange,
  label,
}: {
  id?: string;
  value: number | null;
  onChange: (personId: number | null) => void;
  label?: string;
}) {
  const { t } = useI18n();
  const { data: people } = usePeople();
  return (
    <select
      id={id}
      className="input w-48"
      aria-label={label}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}
    >
      <option value="">{t("members.notLinked")}</option>
      {people?.map((person) => (
        <option key={person.id} value={person.id}>{person.full_name}</option>
      ))}
    </select>
  );
}

/** Rename or delete the project itself. */
function ProjectSettings({ project }: { project: Project }) {
  const { t } = useI18n();
  const { capabilities, refreshProjects, selectProject } = useSession();
  const [name, setName] = useState(project.name);
  const rename = useConfigMutation(
    (value: string) => api.put<Project>("/api/project", { name: value }),
    [keys.settings],
  );
  const remove = useConfigMutation(() => api.del("/api/project"), []);

  return (
    <section className="space-y-2">
      <h3 className="label">{t("members.projectHeading")}</h3>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim())
            rename.mutate(name.trim(), { onSuccess: () => void refreshProjects() });
        }}
      >
        <input
          className="input min-w-52 flex-1"
          aria-label={t("projects.name")}
          maxLength={120}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button className="btn-ghost" type="submit" disabled={rename.isPending}>
          {rename.isSuccess ? <Check className="h-4 w-4" aria-hidden /> : null}
          {t("members.rename")}
        </button>
        {capabilities?.deployment !== "desktop" && (
          <button
            type="button"
            className="btn-ghost text-rose-700 dark:text-rose-400"
            onClick={() => {
              const typed = window.prompt(t("members.deleteConfirm", { name: project.name }));
              if (typed === null) return;
              if (typed.trim() !== project.name) {
                window.alert(t("members.deleteMismatch"));
                return;
              }
              remove.mutate(undefined, {
                onSuccess: async () => {
                  await refreshProjects();
                  selectProject(null);
                },
              });
            }}
          >
            <Trash2 className="h-4 w-4" aria-hidden />
            {t("members.deleteProject")}
          </button>
        )}
      </form>
      <MutationError error={rename.error ?? remove.error} />
    </section>
  );
}

/** Invite links: the website's way in for new members. */
function InviteLinks() {
  const { t, tn, formatDate } = useI18n();
  const { data: invites } = useInvites();
  const { data: people } = usePeople();
  const [role, setRole] = useState<ProjectRole>("STAFF");
  const [personId, setPersonId] = useState<number | null>(null);
  const [days, setDays] = useState(7);
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const create = useConfigMutation(
    (payload: unknown) => api.post<InviteCreated>("/api/project/invites", payload),
    [keys.invites],
  );
  const revoke = useConfigMutation(
    (id: number) => api.del(`/api/project/invites/${id}`),
    [keys.invites],
  );

  const link = created ? `${window.location.origin}/invite/${created.token}` : "";
  const personName = (id: number | null) =>
    id === null ? null : (people?.find((p) => p.id === id)?.full_name ?? `#${id}`);

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // The link is selectable in the field anyway.
    }
  }

  return (
    <section className="space-y-3">
      <h3 className="label">{t("members.inviteHeading")}</h3>
      <p className="text-sm text-slate-500">{t("members.inviteIntro")}</p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setCreated(null);
          create.mutate(
            {
              role,
              person_id: role === "STAFF" ? personId : null,
              expires_in_days: days,
            },
            { onSuccess: (invite) => setCreated(invite) },
          );
        }}
      >
        <div>
          <label className="label" htmlFor="invite-role">{t("members.role")}</label>
          <RoleSelect id="invite-role" value={role} onChange={setRole} />
        </div>
        {role === "STAFF" && (
          <div>
            <label className="label" htmlFor="invite-person">{t("members.linkedPerson")}</label>
            <PersonSelect id="invite-person" value={personId} onChange={setPersonId} />
          </div>
        )}
        <div>
          <label className="label" htmlFor="invite-days">{t("members.validFor")}</label>
          <select
            id="invite-days"
            className="input w-28"
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            {[1, 7, 30].map((n) => (
              <option key={n} value={n}>{tn("members.days", n)}</option>
            ))}
          </select>
        </div>
        <button className="btn-primary" type="submit" disabled={create.isPending}>
          <Link2 className="h-4 w-4" aria-hidden />
          {t("members.createLink")}
        </button>
      </form>
      <p className="text-xs text-slate-500">
        {t(`roleHint.${role}`)} ·{" "}
        {role === "STAFF" && personId === null
          ? t("members.linkMultiUse")
          : t("members.linkSingleUse")}
      </p>

      {created && (
        <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 dark:border-emerald-800 dark:bg-emerald-950/40">
          <p className="mb-2 text-sm">{t("members.linkReady")}</p>
          <div className="flex gap-2">
            <input
              className="input font-mono text-xs"
              dir="ltr"
              readOnly
              value={link}
              aria-label={t("members.inviteLink")}
              onFocus={(event) => event.target.select()}
            />
            <button className="btn-ghost" type="button" onClick={() => void copy()}>
              {copied ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
              {copied ? t("members.copied") : t("members.copy")}
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-500">{t("members.linkOnce")}</p>
        </div>
      )}

      <MutationError error={create.error ?? revoke.error} />

      {Boolean(invites?.length) && (
        <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {invites!.map((invite) => (
            <li key={invite.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="badge bg-slate-100 dark:bg-slate-800">{t(`role.${invite.role}`)}</span>
              {personName(invite.person_id) && <span>{personName(invite.person_id)}</span>}
              <span className="text-xs text-slate-500">
                {invite.single_use
                  ? t("members.singleUse")
                  : tn("members.usedTimes", invite.uses)}
                {" · "}
                {t("members.expires", { date: formatDate(invite.expires_at.slice(0, 10)) })}
              </span>
              <button
                className="btn-ghost ms-auto px-2 py-1 text-xs"
                onClick={() => revoke.mutate(invite.id)}
              >
                {t("members.revoke")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Desktop only: accounts with a password on this computer. */
function LocalAccountForm() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<ProjectRole>("STAFF");
  const [personId, setPersonId] = useState<number | null>(null);
  const create = useConfigMutation(
    (payload: unknown) => api.post<Member>("/api/project/members", payload),
    [keys.members],
  );

  return (
    <section className="space-y-3">
      <h3 className="label">{t("members.addLocal")}</h3>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate(
            {
              email: email.trim(),
              full_name: fullName.trim(),
              password,
              role,
              person_id: role === "STAFF" ? personId : null,
            },
            {
              onSuccess: () => {
                setEmail("");
                setFullName("");
                setPassword("");
                setPersonId(null);
              },
            },
          );
        }}
      >
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label className="label" htmlFor="member-email">{t("login.email")}</label>
            <input id="member-email" className="input" type="email" dir="ltr" required
                   value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="min-w-40 flex-1">
            <label className="label" htmlFor="member-name">{t("people.fullName")}</label>
            <input id="member-name" className="input" required
                   value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="label" htmlFor="member-password">{t("login.password")}</label>
            <input id="member-password" className="input w-56" type="password" required
                   autoComplete="new-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="member-role">{t("members.role")}</label>
            <RoleSelect id="member-role" value={role} onChange={setRole} />
          </div>
          {role === "STAFF" && (
            <div>
              <label className="label" htmlFor="member-person">{t("members.linkedPerson")}</label>
              <PersonSelect id="member-person" value={personId} onChange={setPersonId} />
            </div>
          )}
          <button className="btn-primary" type="submit" disabled={create.isPending}>
            <Plus className="h-4 w-4" aria-hidden />
            {t("members.add")}
          </button>
        </div>
        <p className="text-xs text-slate-500">
          {t(`roleHint.${role}`)} · {t("login.passwordHint")}
        </p>
      </form>
      <MutationError error={create.error} />
    </section>
  );
}

export function MembersAdmin() {
  const { t, formatDate } = useI18n();
  const { user: me, project, capabilities, refreshProjects } = useSession();
  const { data: members, isLoading } = useMembers();
  const desktop = capabilities?.deployment === "desktop";

  const invalidate = [keys.members] as const;
  const update = useConfigMutation(
    ({ id, ...payload }: { id: number } & Record<string, unknown>) =>
      api.put<Member>(`/api/project/members/${id}`, payload),
    invalidate,
  );
  const remove = useConfigMutation(
    (id: number) => api.del(`/api/project/members/${id}`),
    invalidate,
  );
  const setPassword = useConfigMutation(
    ({ id, value }: { id: number; value: string }) =>
      api.post<Member>(`/api/project/members/${id}/password`, { password: value }),
    invalidate,
  );

  if (!project) return null;
  const admins = members?.filter((m) => m.role === "ADMIN").length ?? 0;

  return (
    <StepShell title={t("section.members")} intro={t("members.intro")}>
      <ProjectSettings project={project} />
      {desktop ? <LocalAccountForm /> : <InviteLinks />}

      <MutationError error={update.error ?? remove.error ?? setPassword.error} />

      <section>
        <h3 className="label">{t("members.listHeading")}</h3>
        {isLoading ? (
          <Spinner />
        ) : !members?.length ? (
          <EmptyState title={t("members.empty")} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="th">{t("members.col.account")}</th>
                  <th className="th">{t("members.role")}</th>
                  <th className="th">{t("members.linkedPerson")}</th>
                  <th className="th">{t("members.col.lastSeen")}</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody>
                {members.map((member) => {
                  const isMe = member.user_id === me?.id;
                  const lastAdmin = member.role === "ADMIN" && admins === 1;
                  return (
                    <tr key={member.id} className="border-b border-slate-100 dark:border-slate-800/60">
                      <td className="td">
                        <div className="font-medium">
                          {member.full_name}
                          {isMe && <span className="ms-1 text-xs text-slate-400">({t("members.you")})</span>}
                        </div>
                        <div className="text-xs text-slate-500" dir="ltr">{member.email}</div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {member.has_google && (
                            <span className="badge bg-slate-100 dark:bg-slate-800">Google</span>
                          )}
                          {member.has_password && (
                            <span className="badge bg-slate-100 dark:bg-slate-800">{t("members.password")}</span>
                          )}
                          {member.is_locked && (
                            <span className="badge gap-1 bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300">
                              <ShieldAlert className="h-3 w-3" aria-hidden />
                              {t("members.locked")}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="td">
                        <RoleSelect
                          value={member.role}
                          label={t("members.roleFor", { email: member.email })}
                          disabled={lastAdmin}
                          title={lastAdmin ? t("error.lastAdmin") : undefined}
                          onChange={(role) =>
                            update.mutate(
                              { id: member.id, role },
                              // Stepping down changes what this very screen may show.
                              { onSuccess: () => isMe && void refreshProjects() },
                            )
                          }
                        />
                      </td>
                      <td className="td">
                        <PersonSelect
                          value={member.person_id}
                          label={t("members.personFor", { email: member.email })}
                          onChange={(personId) =>
                            update.mutate(
                              personId === null
                                ? { id: member.id, unlink_person: true }
                                : { id: member.id, person_id: personId },
                              { onSuccess: () => isMe && void refreshProjects() },
                            )
                          }
                        />
                      </td>
                      <td className="td text-xs tabular-nums text-slate-500">
                        {member.last_login_at
                          ? formatDate(member.last_login_at.slice(0, 10))
                          : t("members.never")}
                      </td>
                      <td className="td">
                        <div className="flex justify-end gap-1">
                          {desktop && (
                            <button
                              className="btn-ghost px-2 py-1 text-xs"
                              title={t("members.setPassword")}
                              aria-label={t("members.setPassword")}
                              onClick={() => {
                                const value = window.prompt(
                                  t("members.newPasswordPrompt", { email: member.email }),
                                );
                                if (value) setPassword.mutate({ id: member.id, value });
                              }}
                            >
                              <KeyRound className="h-3.5 w-3.5" aria-hidden />
                            </button>
                          )}
                          {!isMe && (
                            <button
                              className="btn-ghost px-2 py-1 text-xs"
                              disabled={lastAdmin}
                              title={t("members.remove")}
                              aria-label={t("members.removeNamed", { email: member.email })}
                              onClick={() => {
                                if (window.confirm(t("members.removeConfirm", { email: member.email })))
                                  remove.mutate(member.id);
                              }}
                            >
                              <UserMinus className="h-3.5 w-3.5" aria-hidden />
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
      </section>
    </StepShell>
  );
}
