import { useState } from "react";
import { CalendarClock } from "lucide-react";
import { useSession } from "@/hooks/useSession";
import { ErrorNotice, LanguageSwitch } from "@/components/ui";
import { useI18n } from "@/i18n";
import type { MessageKey } from "@/i18n";
import { errorText } from "@/i18n/errors";

const GOOGLE_ERRORS: Record<string, MessageKey> = {
  cancelled: "login.googleCancelled",
  failed: "login.googleFailed",
  // Google authenticates existing accounts; it never creates one.
  "no-account": "login.googleNoAccount",
};

export function LoginPage({ needsSetup }: { needsSetup: boolean }) {
  const { t } = useI18n();
  const { signIn, bootstrap, capabilities } = useSession();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const needsCode = needsSetup && Boolean(capabilities?.setup_code_required);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A failed Google round trip comes back as a redirect, so its reason arrives
  // in the query string rather than a response we could catch.
  const googleErrorKey =
    GOOGLE_ERRORS[new URLSearchParams(window.location.search).get("auth_error") ?? ""];
  const googleError = googleErrorKey ? t(googleErrorKey) : undefined;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (needsSetup) await bootstrap(email, fullName, password, needsCode ? setupCode : undefined);
      else await signIn(email, password);
    } catch (err) {
      setError(errorText(err, t));
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

        {needsSetup && <p className="mb-4 text-sm text-slate-500">{t("login.setupIntro")}</p>}

        <form onSubmit={submit} className="space-y-3">
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
            <div>
              <label className="label" htmlFor="full-name">{t("people.fullName")}</label>
              <input id="full-name" className="input" value={fullName} required
                     onChange={(e) => setFullName(e.target.value)} />
            </div>
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
                   value={password} required onChange={(e) => setPassword(e.target.value)} />
            {needsSetup && (
              <p className="mt-1 text-xs text-slate-500">{t("login.passwordHint")}</p>
            )}
          </div>

          {(error || googleError) && <ErrorNotice message={error ?? googleError!} />}

          <button className="btn-primary w-full justify-center" disabled={busy} type="submit">
            {busy ? t("common.working") : needsSetup ? t("login.createAdminButton") : t("login.signIn")}
          </button>
        </form>

        {/* Hidden rather than shown-and-broken when the deployment has no Google client. */}
        {!needsSetup && capabilities?.google_enabled && (
          <a className="btn-ghost mt-3 w-full justify-center" href="/api/auth/google/authorize">
            {t("login.google")}
          </a>
        )}
      </div>
    </div>
  );
}
