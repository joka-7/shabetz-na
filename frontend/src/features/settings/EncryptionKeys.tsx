import { useId, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Lock, LockOpen } from "lucide-react";
import { ApiError, api } from "@/api/client";
import { MutationError } from "@/features/setup/steps/parts";
import { loadSodium, useMemberKey } from "@/hooks/useMemberKey";
import { useI18n } from "@/i18n";
import {
  KeyMismatchError,
  MIN_PASSPHRASE_LENGTH,
  WrongSecretError,
  createMemberKeys,
  parseRecoveryCode,
  rewrapPassphrase,
  unlockWithPassphrase,
  unlockWithRecoveryCode,
  type MemberKeyRecord,
  type MemberKeyWraps,
  type NewMemberKeys,
} from "@/lib/memberKeys";

const KEY = ["member-key"] as const;

/** The account's stored key, or null when none has been set up yet. */
async function fetchMemberKey(): Promise<MemberKeyRecord | null> {
  try {
    return await api.get<MemberKeyRecord>("/api/keys/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Lets the browser paint "working…" before Argon2id holds the main thread for a second. */
function nextFrame(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 30));
}

/**
 * Settings section for the member's end-to-end encryption key
 * (docs/E2EE-DESIGN.md §4.1, §4.7): set it up, unlock it in this tab, change
 * the encryption passphrase, lock it again.
 *
 * Every secret field opts out of autofill: the encryption passphrase must not
 * be the sign-in password, which the server sees at each sign-in.
 */
export function EncryptionKeys() {
  const { t } = useI18n();
  const stored = useQuery({ queryKey: KEY, queryFn: fetchMemberKey });
  const { secretKey } = useMemberKey();

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-slate-500">{t("keys.heading")}</h3>
      <p className="text-xs text-slate-500">{t("keys.intro")}</p>
      {stored.isPending ? null : stored.data === null ? (
        <SetUpKey />
      ) : stored.data === undefined ? (
        <MutationError error={stored.error} />
      ) : secretKey ? (
        <UnlockedKey record={stored.data} secretKey={secretKey} />
      ) : (
        <UnlockKey record={stored.data} />
      )}
    </div>
  );
}

function Notice({ id, tone, children }: { id?: string; tone: "warn" | "error"; children: string }) {
  const colour =
    tone === "warn" ? "text-amber-700 dark:text-amber-400" : "text-red-600 dark:text-red-400";
  return (
    <p id={id} role="alert" className={`text-xs ${colour}`}>
      {children}
    </p>
  );
}

/** Passphrase and confirmation, checked for length and match before any work. */
function PassphraseFields({
  onSubmit,
  onCancel,
  submitLabel,
  busy,
}: {
  onSubmit: (passphrase: string) => void;
  onCancel?: () => void;
  submitLabel: string;
  busy: boolean;
}) {
  const { t } = useI18n();
  const hintId = useId();
  const [passphrase, setPassphrase] = useState("");
  const [confirm, setConfirm] = useState("");
  const tooShort = passphrase.length > 0 && passphrase.length < MIN_PASSPHRASE_LENGTH;
  const mismatch = confirm.length > 0 && confirm !== passphrase;
  const ready = passphrase.length >= MIN_PASSPHRASE_LENGTH && confirm === passphrase;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (ready) onSubmit(passphrase);
  };

  return (
    <form className="space-y-2" onSubmit={submit}>
      <p className="text-xs text-slate-500">{t("keys.notYourPassword")}</p>
      <label className="block text-xs">
        {t("keys.passphrase")}
        <input
          className="input mt-1"
          type="password"
          autoComplete="off"
          aria-invalid={tooShort}
          aria-describedby={tooShort ? hintId : undefined}
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
        />
      </label>
      <label className="block text-xs">
        {t("keys.passphraseConfirm")}
        <input
          className="input mt-1"
          type="password"
          autoComplete="off"
          aria-invalid={mismatch}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </label>
      {tooShort && <Notice id={hintId} tone="warn">{t("keys.tooShort")}</Notice>}
      {mismatch && <Notice tone="warn">{t("keys.mismatch")}</Notice>}
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary text-sm" type="submit" disabled={!ready || busy}>
          {busy ? t("keys.working") : submitLabel}
        </button>
        {onCancel && (
          <button className="btn-ghost text-sm" type="button" onClick={onCancel}>
            {t("common.cancel")}
          </button>
        )}
      </div>
    </form>
  );
}

/**
 * Whether `typed` is the code's last group, read the way the unlock screen
 * reads a code: a typed O or I counts as 0 or 1.
 */
function endsCodeAs(code: string, typed: string): boolean {
  const group = code.slice(-4);
  if (typed.length !== group.length) return false;
  const expected = parseRecoveryCode(code);
  const candidate = parseRecoveryCode(code.slice(0, -group.length) + typed);
  return expected !== null && candidate !== null && expected.join() === candidate.join();
}

/**
 * Shows a new recovery code once and asks for its last group back, so it
 * cannot be dismissed without having been written down.
 */
function RecoveryCodeCheck({
  code,
  onConfirmed,
  onCancel,
  busy,
}: {
  code: string;
  onConfirmed: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const { t } = useI18n();
  const [typed, setTyped] = useState("");
  const [copied, setCopied] = useState(false);
  const matches = endsCodeAs(code, typed.trim());

  return (
    <div className="space-y-2">
      <p className="text-xs">{t("keys.recoveryIntro")}</p>
      <p dir="ltr" className="select-all rounded-lg bg-slate-100 p-2 text-center font-mono text-sm tracking-wider dark:bg-slate-800">
        {code}
      </p>
      <button
        className="btn-ghost text-sm"
        type="button"
        onClick={() => {
          void navigator.clipboard?.writeText(code).then(
            () => setCopied(true),
            () => setCopied(false),
          );
        }}
      >
        <Copy className="h-4 w-4" aria-hidden />
        {copied ? t("calendar.copied") : t("calendar.copy")}
      </button>
      <label className="block text-xs">
        {t("keys.recoveryConfirm")}
        <input
          dir="ltr"
          className="input mt-1 font-mono"
          autoComplete="off"
          spellCheck={false}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary text-sm" disabled={!matches || busy} onClick={onConfirmed}>
          {busy ? t("keys.working") : t("keys.recoverySaved")}
        </button>
        <button className="btn-ghost text-sm" type="button" onClick={onCancel}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}

function SetUpKey() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { remember } = useMemberKey();
  const [draft, setDraft] = useState<NewMemberKeys | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function makeDraft(passphrase: string) {
    setBusy(true);
    setFailed(false);
    try {
      const sodium = await loadSodium();
      await nextFrame();
      setDraft(createMemberKeys(sodium, passphrase));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  const upload = useMutation({
    mutationFn: (record: MemberKeyRecord) => api.post<MemberKeyRecord>("/api/keys/me", record),
    onSuccess: (saved) => {
      if (draft) remember(draft.secretKey);
      queryClient.setQueryData(KEY, saved);
    },
  });

  if (draft) {
    return (
      <>
        <RecoveryCodeCheck
          code={draft.recoveryCode}
          busy={upload.isPending}
          onConfirmed={() => upload.mutate(draft.record)}
          onCancel={() => setDraft(null)}
        />
        <MutationError error={upload.error} />
      </>
    );
  }
  return (
    <>
      <PassphraseFields submitLabel={t("keys.create")} busy={busy} onSubmit={(p) => void makeDraft(p)} />
      {failed && <Notice tone="error">{t("keys.failed")}</Notice>}
    </>
  );
}

function UnlockKey({ record }: { record: MemberKeyRecord }) {
  const { t } = useI18n();
  const { remember } = useMemberKey();
  const [useCode, setUseCode] = useState(false);
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<"wrong" | "damaged" | "failed" | null>(null);

  async function unlock(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      const sodium = await loadSodium();
      await nextFrame();
      remember(
        useCode
          ? unlockWithRecoveryCode(sodium, record, secret)
          : unlockWithPassphrase(sodium, record, secret),
      );
    } catch (error) {
      if (error instanceof WrongSecretError) setFailure("wrong");
      else if (error instanceof KeyMismatchError) setFailure("damaged");
      // Loading libsodium or running Argon2id failed: offline, out of memory, a stale build.
      else setFailure("failed");
    } finally {
      setBusy(false);
    }
  }

  const message = { wrong: "keys.wrongSecret", damaged: "keys.damaged", failed: "keys.failed" } as const;

  return (
    <form className="space-y-2" onSubmit={(event) => void unlock(event)}>
      <label className="block text-xs">
        {useCode ? t("keys.recoveryCode") : t("keys.passphrase")}
        <input
          // Remounted on switch, so focus lands in the field that is now asked for.
          key={useCode ? "code" : "passphrase"}
          autoFocus
          className="input mt-1"
          type={useCode ? "text" : "password"}
          dir={useCode ? "ltr" : undefined}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={failure === "wrong"}
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
        />
      </label>
      {failure && <Notice tone="error">{t(message[failure])}</Notice>}
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary text-sm" type="submit" disabled={!secret || busy}>
          <LockOpen className="h-4 w-4" aria-hidden />
          {busy ? t("keys.working") : t("keys.unlock")}
        </button>
        <button
          className="btn-ghost text-sm"
          type="button"
          onClick={() => {
            setUseCode(!useCode);
            setSecret("");
            setFailure(null);
          }}
        >
          {useCode ? t("keys.usePassphrase") : t("keys.useRecoveryCode")}
        </button>
      </div>
    </form>
  );
}

function UnlockedKey({ record, secretKey }: { record: MemberKeyRecord; secretKey: Uint8Array }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { forget } = useMemberKey();
  const [changing, setChanging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const upload = useMutation({
    mutationFn: (wraps: MemberKeyWraps) => api.put<MemberKeyRecord>("/api/keys/me/wraps", wraps),
    onSuccess: (saved) => {
      queryClient.setQueryData(KEY, saved);
      setChanging(false);
    },
  });

  async function change(passphrase: string) {
    setBusy(true);
    setFailed(false);
    try {
      const sodium = await loadSodium();
      await nextFrame();
      upload.mutate(rewrapPassphrase(sodium, secretKey, passphrase, record));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  if (changing) {
    return (
      <>
        <PassphraseFields
          submitLabel={t("keys.saveNewPassphrase")}
          busy={busy || upload.isPending}
          onSubmit={(p) => void change(p)}
          onCancel={() => setChanging(false)}
        />
        {failed && <Notice tone="error">{t("keys.failed")}</Notice>}
        <MutationError error={upload.error} />
      </>
    );
  }
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
        <KeyRound className="h-4 w-4" aria-hidden />
        {t("keys.unlocked")}
      </p>
      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost text-sm" onClick={() => setChanging(true)}>
          {t("keys.changePassphrase")}
        </button>
        <button className="btn-ghost text-sm" onClick={forget}>
          <Lock className="h-4 w-4" aria-hidden />
          {t("keys.lock")}
        </button>
      </div>
    </div>
  );
}
