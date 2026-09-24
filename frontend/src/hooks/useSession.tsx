import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, adoptCsrfTokenFromCookie, api, setCsrfToken, setProjectId } from "@/api/client";
import { googleIdToken } from "@/lib/firebase";
import type { Capabilities, Project, ProjectRole, SessionResponse, User } from "@/types/api";

interface SessionState {
  user: User | null;
  capabilities: Capabilities | null;
  loading: boolean;
  /** Every project the account belongs to, with its role in each. */
  projects: Project[];
  /** The project being worked in; null while choosing one. */
  project: Project | null;
  selectProject: (id: number | null) => void;
  createProject: (name: string) => Promise<Project>;
  refreshProjects: () => Promise<Project[]>;
  signIn: (email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  bootstrap: (
    email: string,
    fullName: string,
    password: string,
    organizationName: string,
    setupCode?: string,
  ) => Promise<void>;
  refresh: () => Promise<void>;
  /** Desktop only: set a new password with a reset code, then sign in. */
  resetPassword: (email: string, code: string, password: string) => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

const PROJECT_KEY = "shabetz.project";

function rememberedProject(): number | null {
  try {
    const value = Number(localStorage.getItem(PROJECT_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function rememberProject(id: number | null): void {
  try {
    if (id === null) localStorage.removeItem(PROJECT_KEY);
    else localStorage.setItem(PROJECT_KEY, String(id));
  } catch {
    // Only a convenience: the project picker is shown instead.
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setCurrentProjectId] = useState<number | null>(null);

  const selectProject = useCallback(
    (id: number | null) => {
      // Set before anything refetches, so no request goes to the old project.
      setProjectId(id);
      rememberProject(id);
      // Nothing cached from one organisation may show in another.
      queryClient.clear();
      setCurrentProjectId(id);
    },
    [queryClient],
  );

  const refreshProjects = useCallback(async () => {
    const mine = await api.get<Project[]>("/api/projects");
    setProjects(mine);
    return mine;
  }, []);

  const loadProjects = useCallback(async () => {
    const mine = await refreshProjects();
    const remembered = rememberedProject();
    // Straight into the project last worked in, or the only one there is.
    const pick =
      mine.find((p) => p.id === remembered)?.id ?? (mine.length === 1 ? mine[0]!.id : null);
    selectProject(pick);
  }, [refreshProjects, selectProject]);

  const loadCapabilities = useCallback(async () => {
    setCapabilities(await api.get<Capabilities>("/api/meta/capabilities"));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<User>("/api/auth/me");
      adoptCsrfTokenFromCookie();
      setUser(me);
      await loadProjects();
    } catch (error) {
      // A 401 here is the normal signed-out state, not a failure to report.
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      setUser(null);
      setProjects([]);
    }
  }, [loadProjects]);

  useEffect(() => {
    void (async () => {
      await Promise.all([loadCapabilities(), refresh()]);
      setLoading(false);
    })();
  }, [loadCapabilities, refresh]);

  const adopt = useCallback(
    async (session: SessionResponse) => {
      setCsrfToken(session.csrf_token);
      setUser(session.user);
      await loadProjects();
      await loadCapabilities();
    },
    [loadProjects, loadCapabilities],
  );

  const signIn = useCallback(
    async (email: string, password: string) => {
      await adopt(await api.post<SessionResponse>("/api/auth/login", { email, password }));
    },
    [adopt],
  );

  const signInWithGoogle = useCallback(async () => {
    if (!capabilities?.firebase) return;
    const id_token = await googleIdToken(capabilities.firebase);
    await adopt(await api.post<SessionResponse>("/api/auth/firebase", { id_token }));
  }, [adopt, capabilities]);

  const bootstrap = useCallback(
    async (
      email: string,
      full_name: string,
      password: string,
      organization_name: string,
      setup_code?: string,
    ) => {
      await adopt(
        await api.post<SessionResponse>("/api/setup/bootstrap-admin", {
          email,
          full_name,
          password,
          organization_name,
          setup_code,
        }),
      );
    },
    [adopt],
  );

  const resetPassword = useCallback(
    async (email: string, code: string, password: string) => {
      await adopt(
        await api.post<SessionResponse>("/api/auth/recovery/complete", { email, code, password }),
      );
    },
    [adopt],
  );

  const createProject = useCallback(
    async (name: string) => {
      const created = await api.post<Project>("/api/projects", { name });
      await refreshProjects();
      selectProject(created.id);
      return created;
    },
    [refreshProjects, selectProject],
  );

  const signOut = useCallback(async () => {
    await api.post("/api/auth/logout");
    setCsrfToken(null);
    setUser(null);
    setProjects([]);
    selectProject(null);
  }, [selectProject]);

  const project = projects.find((p) => p.id === projectId) ?? null;

  const value = useMemo(
    () => ({
      user,
      capabilities,
      loading,
      projects,
      project,
      selectProject,
      createProject,
      refreshProjects,
      signIn,
      signInWithGoogle,
      signOut,
      bootstrap,
      refresh,
      resetPassword,
    }),
    [
      user,
      capabilities,
      loading,
      projects,
      project,
      selectProject,
      createProject,
      refreshProjects,
      signIn,
      signInWithGoogle,
      signOut,
      bootstrap,
      refresh,
      resetPassword,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}

const RANK: Record<ProjectRole, number> = { STAFF: 0, COLLABORATOR: 1, ADMIN: 2 };
const atLeast = (project: Project | null, role: ProjectRole) =>
  project !== null && RANK[project.role] >= RANK[role];

/**
 * What the current role may do in the current project, mirroring the server's
 * rules so the interface hides what would only be refused.
 */
export const can = {
  editConfig: (project: Project | null) => atLeast(project, "COLLABORATOR"),
  manageMembers: (project: Project | null) => atLeast(project, "ADMIN"),
  generate: (project: Project | null) => atLeast(project, "COLLABORATOR"),
  reviewTimeOff: (project: Project | null) => atLeast(project, "COLLABORATOR"),
};
