import { useState } from "react";
import { CalendarClock } from "lucide-react";
import { ApiError } from "@/api/client";
import { useSession } from "@/hooks/useSession";
import { ErrorNotice } from "@/components/ui";

const GOOGLE_ERRORS: Record<string, string> = {
  cancelled: "Google sign-in was cancelled.",
  failed: "Google sign-in could not be completed. Please try again.",
  // Google authenticates existing accounts; it never creates one.
  "no-account": "That Google account is not registered here. Ask an administrator to invite it.",
};

export function LoginPage({ needsSetup }: { needsSetup: boolean }) {
  const { signIn, bootstrap, capabilities } = useSession();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A failed Google round trip comes back as a redirect, so its reason arrives
  // in the query string rather than a response we could catch.
  const googleError = GOOGLE_ERRORS[new URLSearchParams(window.location.search).get("auth_error") ?? ""];

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (needsSetup) await bootstrap(email, fullName, password);
      else await signIn(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
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
            {needsSetup ? "Create the first administrator" : "Sign in"}
          </h1>
        </div>

        {needsSetup && (
          <p className="mb-4 text-sm text-slate-500">
            No account exists yet. The account you create here administers the system;
            afterwards this page is closed permanently.
          </p>
        )}

        <form onSubmit={submit} className="space-y-3">
          {needsSetup && (
            <div>
              <label className="label" htmlFor="full-name">Full name</label>
              <input id="full-name" className="input" value={fullName} required
                     onChange={(e) => setFullName(e.target.value)} />
            </div>
          )}
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" className="input" type="email" autoComplete="username"
                   value={email} required onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input id="password" className="input" type="password"
                   autoComplete={needsSetup ? "new-password" : "current-password"}
                   value={password} required onChange={(e) => setPassword(e.target.value)} />
            {needsSetup && (
              <p className="mt-1 text-xs text-slate-500">At least 12 characters.</p>
            )}
          </div>

          {(error || googleError) && <ErrorNotice message={error ?? googleError!} />}

          <button className="btn-primary w-full justify-center" disabled={busy} type="submit">
            {busy ? "Working…" : needsSetup ? "Create administrator" : "Sign in"}
          </button>
        </form>

        {/* Hidden rather than shown-and-broken when the deployment has no Google client. */}
        {!needsSetup && capabilities?.google_enabled && (
          <a className="btn-ghost mt-3 w-full justify-center" href="/api/auth/google/authorize">
            Continue with Google
          </a>
        )}
      </div>
    </div>
  );
}
