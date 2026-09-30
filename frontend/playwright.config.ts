import { defineConfig } from "@playwright/test";

const PORT = 8765;

/**
 * End-to-end tests run the real thing: the built frontend served by the real
 * API on a throwaway SQLite database. Build first (`npm run build`).
 *
 * Set E2E_CHROMIUM to a Chromium binary to use instead of Playwright's own
 * download, and E2E_RUNNER to change how the Python tools are launched.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: process.env.E2E_CHROMIUM
      ? { executablePath: process.env.E2E_CHROMIUM }
      : undefined,
  },
  webServer: {
    command:
      `sh -c 'rm -f /tmp/shabetz-e2e.db && ` +
      `${process.env.E2E_RUNNER ?? "uv run --extra dev"} alembic upgrade head && ` +
      `${process.env.E2E_RUNNER ?? "uv run --extra dev"} uvicorn shabetz.api.main:app --port ${PORT}'`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/meta/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      SHABETZ_DATABASE_URL: "sqlite:////tmp/shabetz-e2e.db",
      SHABETZ_STATIC_DIR: "frontend/dist",
      SHABETZ_COOKIE_SECURE: "false",
      SHABETZ_SECRET_KEY: "e2e-secret-key",
    },
  },
});
