import { expect, test, type Page } from "@playwright/test";

import { api, circularByNumber, PINNED_CIRCULAR } from "./helpers";

/**
 * Screenshot baselines on the seeded synthetic corpus. They were accepted
 * after inspecting each image; a changed image needs the same inspection
 * before `--update-snapshots`, never a blind update. Times and durations are
 * masked because they come from the run, not from the design.
 */

const WIDTHS = [1440, 390] as const;

async function runFor(page: Page): Promise<string> {
  const circular = await circularByNumber(page.request, PINNED_CIRCULAR);
  const runs = await api<{ items: { run_id: string; status: string; circular_id: number }[] }>(
    page.request,
    "/assessments?limit=50",
  );
  const run = runs.items.find((r) => r.status === "COMPLETED" && r.circular_id === circular.id);
  expect(run, "the workflow test leaves a completed run").toBeTruthy();
  return (run as { run_id: string }).run_id;
}

for (const width of WIDTHS) {
  test.describe(`at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("assessment workspace", async ({ page }) => {
      const runId = await runFor(page);
      const detail = await api<{ findings: { id: number; clause_number: string | null }[] }>(
        page.request,
        `/assessments/${runId}`,
      );
      const finding = detail.findings.find((f) => f.clause_number === "A.3") ?? detail.findings[0];
      await page.goto(`/assessments/${runId}?finding=${finding.id}`);
      await expect(page.locator("mark[data-mark=quote]").first()).toBeVisible();
      // The run's duration and finish time change the line's length, and with
      // it where the line wraps at 390px: pin the text, then mask it.
      await page
        .getByText(/finished \d/)
        .evaluate((node) => (node.textContent = " · 50.0 s, finished 15 Oct 2026, 12:00"));
      await expect(page).toHaveScreenshot(`workspace-${width}.png`, {
        fullPage: true,
        mask: [page.getByText(/finished \d/), page.getByText(/^Database up/)],
      });
    });

    test("circular detail", async ({ page }) => {
      const circular = await circularByNumber(page.request, PINNED_CIRCULAR);
      await page.goto(`/circulars/${circular.id}`);
      await expect(page.getByRole("region", { name: "Obligations" })).toBeVisible();
      await expect(page).toHaveScreenshot(`circular-${width}.png`, {
        fullPage: true,
        // Ingestion time differs per database build.
        mask: [page.getByRole("region", { name: "Provenance" }).locator("dd").last()],
      });
    });

    test("point in time", async ({ page }) => {
      const circular = await circularByNumber(page.request, PINNED_CIRCULAR);
      await page.goto(`/point-in-time?circular=${circular.id}&as_of=2024-12-01`);
      await expect(page.getByRole("region", { name: "Timeline" })).toBeVisible();
      await expect(page).toHaveScreenshot(`point-in-time-${width}.png`, { fullPage: true });
    });
  });
}
