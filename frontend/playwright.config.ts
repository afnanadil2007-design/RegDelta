import { defineConfig } from "@playwright/test";

/**
 * Two smoke flows only. They need a seeded database and both servers running:
 *     make seed && make obligations && make dev
 *
 * Playwright is deliberately not wired into CI: the flows depend on a seeded
 * corpus and (for the assessment flow) a provider key, so running them there
 * would produce failures that say nothing about the change under test.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: process.env.REGDELTA_WEB_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
});
