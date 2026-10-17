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

/** The completed run of the pinned circular that the workflow test leaves behind. */
async function completedRun(page: import("@playwright/test").Page): Promise<string> {
  const circular = await circularByNumber(page.request, PINNED_CIRCULAR);
  const runs = await api<{ items: { run_id: string; status: string; circular_id: number }[] }>(
    page.request,
    "/assessments?limit=50",
  );
  const run = runs.items.find((r) => r.status === "COMPLETED" && r.circular_id === circular.id);
  expect(run, "the workflow test leaves a completed run").toBeTruthy();
  return (run as { run_id: string }).run_id;
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

  await page.goto(`/assessments/${await completedRun(page)}`);
  await expect(page.locator("mark[data-mark=quote]").first()).toBeVisible();
  await page.getByRole("button", { name: /Show \d+ steps/ }).click();
  // Scan from the top. Where the click leaves the page depends on how long
  // the trace is, and any control then passing beneath the sticky bar would
  // read as an obscured target; that focus never lands there is tested below.
  await page.evaluate(() => window.scrollTo(0, 0));
  await scan(page);
});

test("the phone layout of the workspace has no axe violations", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/assessments/${await completedRun(page)}`);
  await expect(page.getByRole("combobox")).toBeVisible();
  await scan(page);
});

test("keyboard focus is never hidden under the sticky top bar", async ({ page }) => {
  const runId = await completedRun(page);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/assessments/${runId}`);
    await expect(page.locator("mark[data-mark=quote]").first()).toBeVisible();
    // Walk backwards from the last control: moving up the page is when a
    // focused control can scroll in beneath the bar instead of below it.
    await page.locator("main").getByRole("button").last().focus();
    const hidden: string[] = [];
    for (let step = 0; step < 120; step += 1) {
      await page.keyboard.press("Shift+Tab");
      const focus = await page.evaluate(() => {
        const element = document.activeElement as HTMLElement | null;
        if (!element || element === document.body) return null;
        const bar = document.querySelector("header")?.getBoundingClientRect();
        const box = element.getBoundingClientRect();
        const top = document.elementFromPoint(box.left + box.width / 2, Math.max(box.top, 0) + 1);
        return {
          inBar: Boolean(element.closest("header")),
          covered: Boolean(bar && box.top < bar.bottom && top && !element.contains(top)),
          name: (element.getAttribute("aria-label") ?? element.textContent ?? element.tagName)
            .trim()
            .slice(0, 60),
        };
      });
      if (!focus || focus.inBar) break;
      if (focus.covered) hidden.push(`${width}px: ${focus.name}`);
    }
    expect(hidden, hidden.join("\n")).toEqual([]);
  }
});
