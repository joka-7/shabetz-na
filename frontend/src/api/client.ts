/**
 * API client.
 *
 * Requests are same-origin relative paths so the HttpOnly session cookie is
 * sent automatically; the CSRF token is held in memory and attached to every
 * mutating request, since a cookie alone must not be enough to write.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

/**
 * Recover the CSRF token from its cookie.
 *
 * Sign-in through Google finishes as a redirect rather than a JSON response,
 * so there is no body to read the token from. The server sets it readable for
 * exactly this case; it is useless on its own without the HttpOnly session
 * cookie that accompanies it.
 */
export function adoptCsrfTokenFromCookie(cookieName = "shabetz_csrf"): string | null {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${cookieName}=`));
  if (!match) return null;
  const value = decodeURIComponent(match.slice(cookieName.length + 1));
  if (value) csrfToken = value;
  return value || null;
}

/**
 * The project every request acts on. Each organisation's data lives in its
 * own project, and the server checks membership on every call; the id travels
 * as a header so no route has to spell it out.
 */
let projectId: number | null = null;

export function setProjectId(id: number | null): void {
  projectId = id;
}

export function getProjectId(): number | null {
  return projectId;
}

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  // A FormData body sets its own multipart boundary, so it is left alone.
  if (options.body !== undefined && !(options.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (MUTATING.has(method) && csrfToken) {
    headers.set("x-csrf-token", csrfToken);
  }
  if (projectId !== null && !headers.has("x-project-id")) {
    headers.set("x-project-id", String(projectId));
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const body = text ? JSON.parse(text) : undefined;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.code ?? "UNKNOWN",
      body?.detail ?? response.statusText,
    );
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
      headers,
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  del: (path: string) => request<void>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { method: "POST", body: form });
  },
};

/**
 * Trigger a download through a normal navigation so the cookie is sent. A
 * navigation cannot carry headers, so the project rides in the query string.
 */
export function downloadExport(scheduleId: string, format: string): void {
  const project = projectId === null ? "" : `&project=${projectId}`;
  window.location.href = `/api/schedule/runs/${encodeURIComponent(scheduleId)}/export?format=${format}${project}`;
}
