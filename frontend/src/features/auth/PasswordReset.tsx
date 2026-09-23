import { useState } from "react";
import { FileText, KeyRound } from "lucide-react";
import { api } from "@/api/client";
import { useSession } from "@/hooks/useSession";
import { ErrorNotice } from "@/components/ui";
import { useI18n } from "@/i18n";
import { errorText } from "@/i18n/errors";

/**
 * Desktop-only way back in after forgetting a password.
 *
 * The app writes a one-time code into a file in its own folder and opens it;
 * typing the code back proves the person is at this computer, whose data it is.
 */
export function PasswordReset({ onCancel }: { onCancel: () => void }) {
  const { t } = useI18n();
  const { resetPassword } = useSession();
  const [filePath, setFilePath] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setError(null);
    setBusy(true);
    try {
      const result = await api.post<{ file_path: string }>("/api/auth/recovery/start");
      setFilePath(result.file_path);
    } catch (err) {
      setError(errorText(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await resetPassword(email, code, password);
    } catch (err) {
      setError(errorText(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-medium">
        <KeyRound className="h-4 w-4" aria-hidden />
        {t("reset.title")}
      </h2>

      {!filePath ? (
        <>
          <p className="text-sm text-slate-500">{t("reset.intro")}</p>
          {error && <ErrorNotice message={error} />}
          <button className="btn-primary w-full justify-center" onClick={() => void start()} disabled={busy}>
            <FileText className="h-4 w-4" aria-hidden />
            {busy ? t("common.working") : t("reset.createCode")}
          </button>
        </>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <p className="text-sm text-slate-500">{t("reset.fileOpened")}</p>
          <p className="break-all rounded bg-slate-100 px-2 py-1 font-mono text-xs dark:bg-slate-800" dir="ltr">
            {filePath}
          </p>
          <div>
            <label className="label" htmlFor="reset-email">{t("login.email")}</label>
            <input id="reset-email" className="input" type="email" dir="ltr" required
                   autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="reset-code">{t("reset.code")}</label>
            <input id="reset-code" className="input font-mono uppercase tracking-wider" dir="ltr"
                   required autoComplete="one-time-code" placeholder="XXXX-XXXX-XXXX"
                   value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="reset-password">{t("reset.newPassword")}</label>
            <input id="reset-password" className="input" type="password" required
                   autoComplete="new-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
            <p className="mt-1 text-xs text-slate-500">{t("login.passwordHint")}</p>
          </div>
          {error && <ErrorNotice message={error} />}
          <button className="btn-primary w-full justify-center" type="submit" disabled={busy}>
            {busy ? t("common.working") : t("reset.submit")}
          </button>
          <button type="button" className="btn-ghost w-full justify-center text-xs"
                  onClick={() => void start()} disabled={busy}>
            {t("reset.newCode")}
          </button>
        </form>
      )}

      <button type="button" className="w-full text-center text-xs text-slate-500 underline" onClick={onCancel}>
        {t("reset.back")}
      </button>
    </div>
  );
}
