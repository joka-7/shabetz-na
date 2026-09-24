import { useState } from "react";
import type { ReactNode } from "react";
import { CalendarClock } from "lucide-react";
import { useSession } from "@/hooks/useSession";
import { ErrorNotice, LanguageSwitch } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";
import { GoogleSignInCancelled } from "@/lib/firebase";
import { PasswordReset } from "./PasswordReset";

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="h-4 w-4" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 38.2 44 33 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

export function LoginPage({ needsSetup, banner }: { needsSetup: boolean; banner?: ReactNode }) {
  const { t } = useI18n();
  const { signIn, signInWithGoogle, bootstrap, capabilities } = useSession();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [organization, setOrganization] = useState("");
  const [password, setPassword] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const needsCode = needsSetup && Boolean(capabilities?.setup_code_required);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const google = !needsSetup && Boolean(capabilities?.firebase);
  // With Google offered, the password form is only for accounts made before
  // it was, so it waits behind a link.
  const [showPassword, setShowPassword] = useState(!google);
  // A password that "stopped working" is very often typed with the keyboard
  // switched to Hebrew, or with Caps Lock on; both are invisible in a
  // password field, so they are pointed out.
  const typingHebrew = /[֐-׿]/.test(password);
  const canReset = !needsSetup && Boolean(capabilities?.password_recovery);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (needsSetup) {
        await bootstrap(email, fullName, password, organization, needsCode ? setupCode : undefined);
      } else await signIn(email, password);
    } catch (err) {
      setError(errorText(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function withGoogle() {
    setError(null);
    setBusy(true);
    try {
      await signInWithGoogle();
    } catch (err) {
      if (!(err instanceof GoogleSignInCancelled)) setError(t("login.googleFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <CalendarClock className="h-5 w-5" aria-hidden />
          <h1 className="text-lg font-semibold">
            {needsSetup ? t("login.createAdmin") : t("login.signIn")}
          </h1>
          <LanguageSwitch className="ms-auto" />
        </div>

        {banner}
        {needsSetup && <p className="mb-4 text-sm text-slate-500">{t("login.setupIntro")}</p>}
        {google && <p className="mb-4 text-sm text-slate-500">{t("login.googleIntro")}</p>}

        {resetting ? (
          <PasswordReset onCancel={() => setResetting(false)} />
        ) : (
          <>
            {google && (
              <button
                type="button"
                className="btn-ghost w-full justify-center"
                disabled={busy}
                onClick={() => void withGoogle()}
              >
                <GoogleMark />
                {t("login.google")}
              </button>
            )}

            {google && !showPassword && (
              <button
                type="button"
                className="mt-4 w-full text-center text-xs text-slate-500 underline"
                onClick={() => setShowPassword(true)}
              >
                {t("login.withPassword")}
              </button>
            )}

            {showPassword && (
              <form onSubmit={submit} className={`space-y-3 ${google ? "mt-4 border-t border-slate-200 pt-4 dark:border-slate-800" : ""}`}>
                {/* On a hosted server the first administrator must prove they
                    deployed it; otherwise the site belongs to whoever loads it first. */}
                {needsCode && (
                  <div>
                    <label className="label" htmlFor="setup-code">{t("login.setupCode")}</label>
                    <input
                      id="setup-code"
                      className="input font-mono uppercase tracking-wider"
                      dir="ltr"
                      placeholder="XXXX-XXXX-XXXX"
                      autoComplete="off"
                      value={setupCode}
                      required
                      onChange={(e) => setSetupCode(e.target.value)}
                    />
                    <p className="mt-1 text-xs text-slate-500">{t("login.setupCodeHint")}</p>
                  </div>
                )}
                {needsSetup && (
                  <>
                    <div>
                      <label className="label" htmlFor="organization">{t("rules.orgName")}</label>
                      <input id="organization" className="input" value={organization}
                             onChange={(e) => setOrganization(e.target.value)} />
                    </div>
                    <div>
                      <label className="label" htmlFor="full-name">{t("people.fullName")}</label>
                      <input id="full-name" className="input" value={fullName} required
                             onChange={(e) => setFullName(e.target.value)} />
                    </div>
                  </>
                )}
                <div>
                  <label className="label" htmlFor="email">{t("login.email")}</label>
                  <input id="email" className="input" type="email" autoComplete="username" dir="ltr"
                         value={email} required onChange={(e) => setEmail(e.target.value)} />
                </div>
                <div>
                  <label className="label" htmlFor="password">{t("login.password")}</label>
                  <input id="password" className="input" type="password"
                         autoComplete={needsSetup ? "new-password" : "current-password"}
                         value={password} required onChange={(e) => setPassword(e.target.value)}
                         onKeyUp={(e) => setCapsLock(e.getModifierState("CapsLock"))} />
                  {typingHebrew && (
                    <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{t("login.hebrewKeyboard")}</p>
                  )}
                  {capsLock && (
                    <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{t("login.capsLock")}</p>
                  )}
                  {needsSetup && (
                    <p className="mt-1 text-xs text-slate-500">{t("login.passwordHint")}</p>
                  )}
                </div>

                <button className={`${google ? "btn-ghost" : "btn-primary"} w-full justify-center`} disabled={busy} type="submit">
                  {busy ? t("common.working") : needsSetup ? t("login.createAdminButton") : t("login.signIn")}
                </button>
              </form>
            )}

            {error && <div className="mt-3"><ErrorNotice message={error} /></div>}

            {canReset && (
              <button
                type="button"
                className="mt-3 w-full text-center text-xs text-slate-500 underline"
                onClick={() => setResetting(true)}
              >
                {t("login.forgot")}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
