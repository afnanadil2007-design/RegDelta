import { expect, test, type Page } from "@playwright/test";

import { api, circularByNumber, PINNED_CIRCULAR } from "./helpers";

/**
 * Failures injected at the network boundary of an otherwise real session:
 * every request not named here reaches the real API.
 */

async function completedRun(page: Page): Promise<string> {
  const circular = await circularByNumber(page.request, PINNED_CIRCULAR);
  const runs = await api<{ items: { run_id: string; status: string; circular_id: number }[] }>(
    page.request,
    "/assessments?limit=50",
  );
  const run = runs.items.find((r) => r.status === "COMPLETED" && r.circular_id === circular.id);
  expect(run, "the workflow test leaves a completed run").toBeTruthy();
  return (run as { run_id: string }).run_id;
}

test("a failed decision is reported, the old decision stays, and a retry saves it", async ({ page }) => {
  const runId = await completedRun(page);
  await page.goto(`/assessments/${runId}`);
  const accept = page.getByRole("button", { name: "Accept" });
  await expect(accept).toHaveAttribute("aria-pressed", "false");

  await page.route("**/api/assessments/findings/*/decision", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: "database_unavailable", message: "The database did not answer." } },
    }),
  );
  await accept.click();
  await expect(page.getByText("The decision was not saved")).toBeVisible();
  await expect(page.getByText(/The database did not answer\./)).toBeVisible();
  await expect(accept).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByText("Not yet decided").first()).toBeVisible();

  await page.unroute("**/api/assessments/findings/*/decision");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(accept).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("The decision was not saved")).toBeHidden();

  await page.getByRole("button", { name: "Clear" }).click();
  await expect(accept).toHaveAttribute("aria-pressed", "false");
});

test("an unreachable API is explained and Try again recovers without losing filters", async ({ page }) => {
  const isApi = (url: URL) => url.pathname.startsWith("/api/");
  await page.route(isApi, (route) => route.fulfill({ status: 502, body: "Bad gateway" }));
  await page.goto("/circulars?q=margin");
  await expect(page.getByText("The API is not reachable")).toBeVisible();
  await expect(page.getByText("API not reachable")).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Number or title" })).toHaveValue("margin");

  await page.unroute(isApi);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("region", { name: "Circulars" }).getByRole("row").nth(1)).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Number or title" })).toHaveValue("margin");
});

test("a live trace that drops resyncs from the server's snapshot", async ({ page }) => {
  const runId = await completedRun(page);
  const stored = await api<Record<string, unknown>>(page.request, `/assessments/${runId}`);
  const steps = await api<{ seq: number; status: string }[]>(page.request, `/assessments/${runId}/steps`);

  // The run is presented as still running, so the page opens the live stream.
  let running = true;
  await page.route(`**/api/assessments/${runId}`, (route) =>
    route.fulfill({ json: running ? { ...stored, status: "RUNNING", completed_at: null } : stored }),
  );
  let connections = 0;
  await page.route(`**/api/assessments/${runId}/stream`, (route) => {
    connections += 1;
    const snapshot = { status: "RUNNING", steps: steps.slice(0, 3) };
    const body =
      connections === 1
        ? // First connection: a snapshot, then the server ends the stream with an error.
          `event: snapshot\ndata: ${JSON.stringify(snapshot)}\n\nevent: error\ndata: {"message":"Simulated stream failure."}\n\n`
        : // After Reconnect: the full trace and the terminal event.
          `event: snapshot\ndata: ${JSON.stringify({ status: "RUNNING", steps })}\n\nevent: done\ndata: {"status":"COMPLETED"}\n\n`;
    return route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body });
  });

  await page.goto(`/assessments/${runId}`);
  await expect(page.getByText("The live trace stopped")).toBeVisible();
  await expect(page.getByText("Simulated stream failure.")).toBeVisible();

  running = false;
  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  await expect(page.getByText("The live trace stopped")).toBeHidden();
  expect(connections).toBe(2);
});
