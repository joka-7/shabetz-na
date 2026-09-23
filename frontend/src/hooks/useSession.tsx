import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, adoptCsrfTokenFromCookie, api, setCsrfToken } from "@/api/client";
import type { Capabilities, SessionResponse, User } from "@/types/api";

interface SessionState {
  user: User | null;
  capabilities: Capabilities | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  bootstrap: (
    email: string,
    fullName: string,
    password: string,
    setupCode?: string,
  ) => Promise<void>;
  refresh: () => Promise<void>;
  /** Desktop only: set a new password with a reset code, then sign in. */
  resetPassword: (email: string, code: string, password: string) => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [loading, setLoading] = useState(true);

  const loadCapabilities = useCallback(async () => {
    setCapabilities(await api.get<Capabilities>("/api/meta/capabilities"));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<User>("/api/auth/me");
      // A session may already exist from a Google redirect, which carried its
      // CSRF token in a cookie rather than a response body.
      adoptCsrfTokenFromCookie();
      setUser(me);
    } catch (error) {
      // A 401 here is the normal signed-out state, not a failure to report.
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      setUser(null);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await Promise.all([loadCapabilities(), refresh()]);
      setLoading(false);
    })();
  }, [loadCapabilities, refresh]);

  const adopt = useCallback((session: SessionResponse) => {
    setCsrfToken(session.csrf_token);
    setUser(session.user);
  }, []);

  const signIn = useCallback(
    async (email: string, password: string) => {
      adopt(await api.post<SessionResponse>("/api/auth/login", { email, password }));
      await loadCapabilities();
    },
    [adopt, loadCapabilities],
  );

  const bootstrap = useCallback(
    async (email: string, full_name: string, password: string, setup_code?: string) => {
      adopt(
        await api.post<SessionResponse>("/api/setup/bootstrap-admin", {
          email,
          full_name,
          password,
          setup_code,
        }),
      );
      await loadCapabilities();
    },
    [adopt, loadCapabilities],
  );

  const resetPassword = useCallback(
    async (email: string, code: string, password: string) => {
      adopt(
        await api.post<SessionResponse>("/api/auth/recovery/complete", { email, code, password }),
      );
      await loadCapabilities();
    },
    [adopt, loadCapabilities],
  );

  const signOut = useCallback(async () => {
    await api.post("/api/auth/logout");
    setCsrfToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, capabilities, loading, signIn, signOut, bootstrap, refresh, resetPassword }),
    [user, capabilities, loading, signIn, signOut, bootstrap, refresh, resetPassword],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}

/** Capability checks mirroring the server's rules, for hiding what a role cannot use. */
export const can = {
  editConfig: (user: User | null) => user?.role === "ADMIN",
  manageUsers: (user: User | null) => user?.role === "ADMIN",
  generate: (user: User | null) => user?.role === "ADMIN" || user?.role === "SCHEDULER",
  reviewTimeOff: (user: User | null) => user?.role === "ADMIN" || user?.role === "SCHEDULER",
};
