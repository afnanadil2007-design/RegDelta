import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the real API and a disposable database, with the
 * deterministic rule-based judge at the provider boundary (no model calls).
 *
 *     make e2e-db       # creates and seeds the disposable regdelta_e2e database
 *     make e2e          # runs the specs
 *
 * Both servers are started here: the API on 8020 against REGDELTA_E2E_DB and a
 * production build of the frontend on 4180. Point REGDELTA_WEB_URL at running
 * servers to reuse them instead.
 */
const apiPort = Number(process.env.REGDELTA_E2E_API_PORT ?? 8020);
const webPort = Number(process.env.REGDELTA_E2E_WEB_PORT ?? 4180);
const python = process.env.REGDELTA_PYTHON ?? "python";
const database = process.env.REGDELTA_E2E_DB ?? "regdelta_e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: {
    timeout: 15_000,
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled", stylePath: "./e2e/screenshot.css" },
  },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  snapshotPathTemplate: "{testDir}/__screenshots__/{testFilePath}/{arg}{ext}",
  use: {
    baseURL: process.env.REGDELTA_WEB_URL ?? `http://127.0.0.1:${webPort}`,
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: "en-GB",
    timezoneId: "Asia/Kolkata",
    contextOptions: { reducedMotion: "reduce" },
    trace: "retain-on-failure",
  },
  // The workflow test creates the completed run the other files inspect.
  projects: [
    { name: "workflow", testMatch: /workflow\.spec\.ts/ },
    { name: "app", testIgnore: /workflow\.spec\.ts/, dependencies: ["workflow"] },
  ],
  webServer: process.env.REGDELTA_WEB_URL
    ? undefined
    : [
        {
          command: `${python} run_api.py --port ${apiPort}`,
          cwd: "../backend",
          url: `http://127.0.0.1:${apiPort}/api/health`,
          timeout: 120_000,
          reuseExistingServer: !process.env.CI,
          env: {
            POSTGRES_DB: database,
            LLM_PROVIDER: "deterministic",
            WARM_MODELS_ON_STARTUP: "true",
            HF_HUB_OFFLINE: process.env.HF_HUB_OFFLINE ?? "0",
          },
        },
        {
          command: `npm run build && npx vite preview --port ${webPort}`,
          url: `http://127.0.0.1:${webPort}`,
          timeout: 180_000,
          reuseExistingServer: !process.env.CI,
          env: { REGDELTA_API_URL: `http://127.0.0.1:${apiPort}`, REGDELTA_WEB_PORT: String(webPort) },
        },
      ],
});
