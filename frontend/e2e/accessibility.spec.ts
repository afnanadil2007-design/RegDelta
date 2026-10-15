import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { api, circularByNumber, PINNED_CIRCULAR } from "./helpers";

/**
 * An automated WCAG 2.2 A/AA scan of every route. It supplements, and does
 * not replace, the keyboard and screen checks recorded in the ledger: axe
 * finds missing names, roles and contrast, not whether a flow makes sense.
 */

async function scan(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s) — ${v.help}`,
  );
  expect(summary, summary.join("\n")).toEqual([]);
}

test("overview, circulars, search, assessments, point in time, evaluation and 404 have no axe violations", async ({
  page,
}) => {
  for (const path of [
    "/",
    "/circulars",
    "/search",
    "/assessments",
    "/point-in-time",
    "/evaluation",
    "/nope",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await scan(page);
  }
});

test("circular detail and the assessment workspace have no axe violations", async ({ page }) => {
  const circular = await circularByNumber(page.request, PINNED_CIRCULAR);
  await page.goto(`/circulars/${circular.id}`);
  await expect(page.getByRole("region", { name: "Obligations" })).toBeVisible();
  await scan(page);

  const runs = await api<{ items: { run_id: string; status: string; circular_id: number }[] }>(
    page.request,
    "/assessments?limit=50",
  );
  const run = runs.items.find((r) => r.status === "COMPLETED" && r.circular_id === circular.id);
  expect(run).toBeTruthy();
  await page.goto(`/assessments/${run?.run_id}`);
  await expect(page.locator("mark[data-mark=quote]").first()).toBeVisible();
  await page.getByRole("button", { name: /Show \d+ steps/ }).click();
  await scan(page);
});

test("the phone layout of the workspace has no axe violations", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const circular = await circularByNumber(page.request, PINNED_CIRCULAR);
  const runs = await api<{ items: { run_id: string; status: string; circular_id: number }[] }>(
    page.request,
    "/assessments?limit=50",
  );
  const run = runs.items.find((r) => r.status === "COMPLETED" && r.circular_id === circular.id);
  await page.goto(`/assessments/${run?.run_id}`);
  await expect(page.getByRole("combobox")).toBeVisible();
  await scan(page);
});
