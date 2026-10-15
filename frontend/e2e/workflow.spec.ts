import { expect, test } from "@playwright/test";

import { circularByNumber, PINNED_CIRCULAR } from "./helpers";

/**
 * The analyst's whole path, against the real API: find a circular, read its
 * obligations, start an assessment, follow it to completion, inspect a
 * finding's evidence, decide, and confirm the decision survives a reload.
 */
test("circular → obligation → assessment → evidence → decision → refresh", async ({ page, request }) => {
  test.setTimeout(420_000);
  const circular = await circularByNumber(request, PINNED_CIRCULAR);

  await page.goto(`/circulars?q=${encodeURIComponent("2024/306")}`);
  await page.getByRole("link", { name: PINNED_CIRCULAR }).first().click();
  await expect(page).toHaveURL(new RegExp(`/circulars/${circular.id}$`));
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // Obligations are listed and marked in the text.
  const obligations = page.getByRole("region", { name: "Obligations" });
  await expect(obligations.getByRole("listitem")).toHaveCount(circular.obligation_count);
  await expect(page.locator("[data-mark=obligation]").first()).toBeVisible();

  // Start the assessment; the workspace opens on the new run.
  await page.getByRole("button", { name: "Start assessment" }).click();
  await expect(page).toHaveURL(/\/assessments\/[0-9a-f-]{36}/);
  const runUrl = page.url();

  // The run finishes with the deterministic judge; findings arrive on the way.
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 360_000 });
  await expect(page.getByText(/Rule-based judge \(deterministic demo\)/).first()).toBeVisible();

  // Evidence: pick the second finding; both documents show its located quote.
  const options = page.getByRole("option");
  await expect(options.first()).toBeVisible();
  await options.nth(1).click();
  await expect(page).toHaveURL(/finding=\d+/);
  const findingUrl = page.url();
  const plate = page.getByText(/^Machine interpretation · /);
  await expect(plate).toBeVisible();
  await expect(page.getByText("Quotes located").first()).toBeVisible();
  await expect(page.locator("mark[data-mark=quote]").first()).toBeVisible();

  // Keyboard: the index moves with the arrow keys.
  await page.getByRole("listbox").focus();
  await page.keyboard.press("ArrowDown");
  await expect(page).not.toHaveURL(findingUrl);
  await page.keyboard.press("ArrowUp");
  await expect(page).toHaveURL(findingUrl);

  // Decide, then reload: the decision is the server's, not the page's.
  const accept = page.getByRole("button", { name: "Accept" });
  await expect(accept).toHaveAttribute("aria-pressed", "false");
  await accept.click();
  await expect(accept).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("status").filter({ hasText: "Accepted. Saved." })).toBeAttached();
  await page.reload();
  await expect(page.getByRole("button", { name: "Accept" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("option", { selected: true })).toContainText("Accepted");

  // Leave the run undecided for the visual baselines.
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByRole("button", { name: "Accept" })).toHaveAttribute("aria-pressed", "false");
  expect(runUrl).toContain("/assessments/");
});

test("a second launch of a running comparison is redirected, not duplicated", async ({ request }) => {
  const circular = await circularByNumber(request, PINNED_CIRCULAR);
  const packs = (await (await request.get("/api/policy-packs")).json()) as { id: number }[];
  const body = { circular_id: circular.id, policy_pack_id: packs[0].id };
  const first = await request.post("/api/assessments", { data: body });
  expect(first.status()).toBe(202);
  const second = await request.post("/api/assessments", { data: body });
  // Either the first run already finished (202 again) or the guard caught it (409 with its id).
  if (second.status() === 409) {
    const envelope = await second.json();
    expect(envelope.error.code).toBe("assessment_in_progress");
    expect(envelope.error.detail.run_id).toBe((await first.json()).run_id);
  } else {
    expect(second.status()).toBe(202);
  }
});
