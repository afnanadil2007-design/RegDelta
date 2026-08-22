import { expect, test } from "@playwright/test";

/**
 * Two smoke flows, as specified. These are deliberately not a full UI suite:
 * component behaviour is covered by Vitest, and these exist to catch the
 * integration failures unit tests cannot — routing, data fetching, and the
 * SSE stream wiring.
 *
 * They require the API and web servers running with a seeded database:
 *     make seed && make obligations && make dev
 */

test.describe("run-an-assessment flow", () => {
  test("navigate to a circular and start an assessment", async ({ page }) => {
    await page.goto("/circulars");

    // The list renders real corpus rows.
    const firstReference = page.locator("table tbody tr a").first();
    await expect(firstReference).toBeVisible();
    await firstReference.click();

    // Circular detail shows obligations and the amendment chain.
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Amendment chain")).toBeVisible();
    await expect(page.getByText("Source text")).toBeVisible();

    // Starting an assessment routes to the assessment screen, which shows the
    // agent trace immediately rather than a whole-page spinner.
    const runButton = page.getByRole("button", { name: /run impact assessment/i });
    await expect(runButton).toBeEnabled();
    await runButton.click();

    await expect(page).toHaveURL(/\/assessments\/[0-9a-f-]{36}/);
    await expect(page.getByText("Agent trace")).toBeVisible();
  });
});

test.describe("point-in-time flow", () => {
  test("ask a question as of a date and get an answer or an explicit refusal", async ({
    page,
  }) => {
    await page.goto("/point-in-time");

    await page.getByLabel("Question").fill("margin collection reporting timeline");
    await page.getByLabel("As of").fill("2023-06-30");
    await page.getByRole("button", { name: "Ask" }).click();

    // Either results in force on that date, or an explicit refusal — never a
    // silent empty page.
    const results = page.getByText(/In force on/);
    const refusal = page.getByText(/answers this question confidently/);
    await expect(results.or(refusal)).toBeVisible({ timeout: 60_000 });
  });
});
