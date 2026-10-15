import { expect, test } from "@playwright/test";

import { dayBefore, supersededCircular } from "./helpers";

test.describe("search", () => {
  test("hybrid search returns passages and a shared link restores them", async ({ page }) => {
    await page.goto("/search");
    await page
      .getByRole("searchbox", { name: "Search the circulars" })
      .fill("client due diligence before account activation");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByText(/passages · Hybrid · answered in/)).toBeVisible();
    await expect(page).toHaveURL(/q=client\+due\+diligence/);
    const first = page.getByRole("region", { name: "Search results" }).getByRole("listitem").first();
    await expect(first.getByRole("link")).toBeVisible();
    await expect(first.locator("mark").first()).toBeVisible();

    await page.reload();
    await expect(page.getByText(/passages · Hybrid · answered in/)).toBeVisible();
  });

  test("an empty query is explained, not sent", async ({ page }) => {
    await page.goto("/search");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByText("Type what you are looking for.")).toBeVisible();
    await expect(page.getByRole("searchbox", { name: "Search the circulars" })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  test("the reranked mode refuses a question the corpus cannot answer", async ({ page }) => {
    test.setTimeout(240_000);
    await page.goto("/search");
    await page
      .getByRole("searchbox", { name: "Search the circulars" })
      .fill("What is the capital of France?");
    await page.getByRole("radio", { name: "Hybrid + rerank" }).check({ force: true });
    await page.getByRole("button", { name: "Search", exact: true }).click();
    // A cancel button and a running clock while the cross-encoder works.
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expect(page.getByText("No passage was relevant enough to show")).toBeVisible({ timeout: 220_000 });
    await expect(page.getByText(/below the refusal threshold of 0\.35/)).toBeVisible();
  });
});

test.describe("point in time", () => {
  test("a superseded circular is in force the day before the effective date and out of force on it", async ({
    page,
    request,
  }) => {
    const { id, effective } = await supersededCircular(request);

    await page.goto(`/point-in-time?circular=${id}&as_of=${dayBefore(effective)}`);
    const timeline = page.getByRole("region", { name: "Timeline" });
    await expect(timeline.getByText(/In force on/).first()).toBeVisible();
    await expect(timeline.getByText("Chosen date")).toBeVisible();

    await page.goto(`/point-in-time?circular=${id}&as_of=${effective}`);
    await expect(
      page
        .getByRole("region", { name: "Timeline" })
        .getByText(/Out of force on/)
        .first(),
    ).toBeVisible();
  });

  test("searching on a date reports what the date filter removed", async ({ page, request }) => {
    test.setTimeout(180_000);
    const { id, effective } = await supersededCircular(request);
    const detail = (await (await request.get(`/api/circulars/${id}`)).json()) as {
      circular: { title: string };
    };
    await page.goto(`/point-in-time?as_of=${effective}`);
    await page.getByRole("searchbox", { name: "What were the rules on…" }).fill(detail.circular.title);
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByText(/passages · Hybrid · answered in|Nothing matched/)).toBeVisible({
      timeout: 120_000,
    });
    await expect(page.getByText(/left out: not in force on/)).toBeVisible();
  });
});

test("the evaluation page shows stored results with provenance, or says there are none", async ({ page }) => {
  await page.goto("/evaluation");
  await expect(page.getByRole("heading", { level: 1, name: "Evaluation" })).toBeVisible();
  const table = page.getByRole("region", { name: /Retrieval metrics by mode/ });
  const empty = page.getByText("No evaluation has been recorded in this database");
  await expect(table.or(empty)).toBeVisible();
  if (await table.isVisible()) {
    await expect(page.getByText(/^Code$/).first()).toBeVisible();
    await expect(page.getByText(/Synthetic corpus/).first()).toBeVisible();
  }
});
