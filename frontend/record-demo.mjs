/** Local browser walkthrough; see docs/maintenance/final-handoff-2026-10-17.md. */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";

const baseURL = "http://127.0.0.1:5173";
const runId = process.env.DEMO_RUN_ID ?? "98dc9b79-d75e-49d1-900a-83dbd8daf85f";
assert.match(runId, /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i);
const output = fileURLToPath(new URL(`../.artifacts/demo/${Date.now()}-${process.pid}/`, import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: process.env.DEMO_HEADED !== "1" });
const context = await browser.newContext({
  baseURL,
  viewport: { width: 1440, height: 900 },
  locale: "en-GB",
  timezoneId: "Asia/Kolkata",
  reducedMotion: "reduce",
  recordVideo: { dir: output, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();
page.setDefaultTimeout(20_000);
const video = page.video();
const pause = (ms) => page.waitForTimeout(ms); // Intentional narration/reading time.
let complete = false;
let chosen;
try {
  const healthResponse = await context.request.get("/api/health");
  assert(healthResponse.ok(), "Local API health request failed");
  const health = await healthResponse.json();
  assert.equal(health.database, "up");
  assert.equal(health.provider.deterministic, true, "Launch the deterministic API first");
  const response = await context.request.get(`/api/assessments/${runId}`);
  assert(response.ok(), "Existing run is unavailable");
  const run = await response.json();
  assert.equal(run.status, "COMPLETED");
  assert.equal(run.provider?.deterministic, true, "Use a completed deterministic run");
  chosen = run.findings.find(
    (f) =>
      f.analyst_decision === "PENDING" &&
      f.quote_status === "VERIFIED" &&
      f.circular_span_start != null &&
      f.clause_span_start != null,
  );
  assert(chosen, "No pending finding with both quotes; choose another deterministic run");

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await pause(20_000);
  await page.goto(`/circulars/${run.circular_id}`);
  await expect(page.getByRole("region", { name: "Obligations" })).toBeVisible();
  await expect(page.locator("[data-mark=obligation]").first()).toBeVisible();
  await pause(25_000);
  await page.goto(`/assessments/${runId}?finding=${chosen.id}`);
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  await expect(page.getByText(/Rule-based judge \(deterministic demo\)/).first()).toBeVisible();
  await expect(page.getByText("Quotes located").first()).toBeVisible();
  await expect(page.locator("mark[data-mark=quote]").first()).toBeVisible();
  await page.screenshot({ path: `${output}/evidence.png` });
  await pause(45_000);

  // Recheck immediately before mutating; preserve any pre-existing decision.
  const freshResponse = await context.request.get(`/api/assessments/${runId}`);
  assert(freshResponse.ok());
  const fresh = await freshResponse.json();
  assert.equal(fresh.findings.find((f) => f.id === chosen.id)?.analyst_decision, "PENDING");
  const accept = page.getByRole("button", { name: "Accept", exact: true });
  await expect(accept).toHaveAttribute("aria-pressed", "false");
  await accept.click();
  await expect(accept).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("status").filter({ hasText: "Accepted. Saved." })).toBeAttached();
  await pause(10_000);
  await page.reload();
  await expect(page.getByRole("button", { name: "Accept", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("option", { selected: true })).toContainText("Accepted");
  await page.screenshot({ path: `${output}/persisted.png` });
  await pause(20_000);
  await page.goto("/evaluation");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await pause(45_000);
  complete = true;
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
  throw error;
} finally {
  // Closing the context finalizes the WebM, including on failure.
  await context.close();
  const videoPath = await video.path();
  await browser.close();
  await writeFile(
    `${output}/capture.json`,
    JSON.stringify(
      {
        complete,
        runId,
        findingId: chosen?.id,
        videoPath,
        note: "Silent browser capture. Inspect playback before sharing. Accept remains saved if reached.",
      },
      null,
      2,
    ) + "\n",
  );
  console.log(JSON.stringify({ complete, output, videoPath }));
}
