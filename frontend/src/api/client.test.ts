import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, apiFetch } from "@/api/client";

function respond(body: string, status: number, contentType = "application/json") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status, headers: { "Content-Type": contentType } })),
  );
}

async function failure(): Promise<ApiRequestError> {
  try {
    await apiFetch("/health");
  } catch (error) {
    if (error instanceof ApiRequestError) return error;
    throw error;
  }
  throw new Error("the request did not fail");
}

afterEach(() => vi.unstubAllGlobals());

describe("apiFetch error mapping", () => {
  it("keeps the API's own error code and message", async () => {
    respond('{"error":{"code":"provider_unavailable","message":"Set GROQ_API_KEY.","detail":null}}', 503);
    const error = await failure();
    expect([error.code, error.status, error.message]).toEqual([
      "provider_unavailable",
      503,
      "Set GROQ_API_KEY.",
    ]);
  });

  it("reports the web proxy's unreachable answer as an unreachable API", async () => {
    respond(
      '{"error":{"code":"api_unreachable","message":"The web server could not reach the RegDelta API.","detail":null}}',
      502,
    );
    const error = await failure();
    expect([error.code, error.status]).toEqual(["network_error", 502]);
    expect(error.message).toContain("could not reach");
  });

  it("keeps a proxy timeout distinct from an unreachable API", async () => {
    respond(
      '{"error":{"code":"api_timeout","message":"The RegDelta API did not answer.","detail":null}}',
      504,
    );
    expect((await failure()).code).toBe("api_timeout");
  });

  it("treats an HTML gateway page as unreachable rather than parsing it", async () => {
    respond("<html><body>502 Bad Gateway</body></html>", 502, "text/html");
    expect((await failure()).code).toBe("network_error");
  });
});
