import { expect, type APIRequestContext } from "@playwright/test";

/** Read-only lookups against the same API the browser uses, to pick test subjects from data. */
export async function api<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`/api${path}`);
  expect(response.ok(), `GET /api${path} -> ${response.status()}`).toBeTruthy();
  return (await response.json()) as T;
}

interface Summary {
  id: number;
  circular_number: string;
  obligation_count: number;
  issue_date: string | null;
}

interface Edge {
  direction: "incoming" | "outgoing";
  superseded_circular_id: number | null;
  removes_from_force: boolean;
  resolved: boolean;
  effective_date: string | null;
}

/** A circular by its number, from the list endpoint's text filter. */
export async function circularByNumber(request: APIRequestContext, number: string): Promise<Summary> {
  const page = await api<{ items: Summary[] }>(request, `/circulars?q=${encodeURIComponent(number)}&limit=5`);
  const match = page.items.find((c) => c.circular_number === number);
  expect(match, `circular ${number} is in the e2e database`).toBeTruthy();
  return match as Summary;
}

/** An older circular that a newer one takes out of force on a recorded date. */
export async function supersededCircular(
  request: APIRequestContext,
): Promise<{ id: number; effective: string }> {
  const page = await api<{ items: Summary[] }>(request, "/circulars?limit=40");
  for (const circular of page.items) {
    const detail = await api<{ supersessions: Edge[] }>(request, `/circulars/${circular.id}`);
    const edge = detail.supersessions.find(
      (s) =>
        s.direction === "outgoing" &&
        s.removes_from_force &&
        s.resolved &&
        s.effective_date &&
        s.superseded_circular_id,
    );
    if (edge) return { id: edge.superseded_circular_id as number, effective: edge.effective_date as string };
  }
  throw new Error("No resolved supersession among the 40 newest circulars");
}

/** The day before an ISO date. */
export function dayBefore(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

/** The circular every visual baseline and the workflow test are pinned to. */
export const PINNED_CIRCULAR = "SEBI/HO/MIRSD/MIRSD_Div1/P/CIR/2024/306";
