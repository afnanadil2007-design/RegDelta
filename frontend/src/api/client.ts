import type { ErrorEnvelope } from "@/types/api";

// Single API base. In dev, Vite proxies /api to the backend; built assets are
// served behind the same relative path. There is no other origin.
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

/** One error type for every way a request can fail, so views can explain it. */
export class ApiRequestError extends Error {
  constructor(
    /** Backend error code, or network_error / http_error / parse_error. */
    public readonly code: string,
    message: string,
    /** HTTP status; 0 when no response arrived. */
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

const UNREACHABLE =
  "The RegDelta API could not be reached. Check that the API server is running, then try again.";

// The web container's proxy answers with this code when it cannot reach the
// API (frontend/nginx/default.conf.template). To the reader that is the same
// as no response at all, so it is reported as unreachable.
const PROXY_UNREACHABLE = "api_unreachable";

/** Typed fetch that unwraps the backend's {error:{code,message,detail}} envelope. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiRequestError("network_error", UNREACHABLE, 0);
  }

  if (!response.ok) {
    let envelope: ErrorEnvelope | null = null;
    try {
      envelope = (await response.json()) as ErrorEnvelope;
    } catch {
      // A proxy error page or an empty body: no envelope to read.
    }
    if (envelope?.error?.code) {
      throw new ApiRequestError(
        envelope.error.code === PROXY_UNREACHABLE ? "network_error" : envelope.error.code,
        envelope.error.message,
        response.status,
        envelope.error.detail,
      );
    }
    const unreachable = response.status === 502 || response.status === 504;
    throw new ApiRequestError(
      unreachable ? "network_error" : "http_error",
      unreachable ? UNREACHABLE : `The request failed with HTTP ${response.status}.`,
      response.status,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiRequestError("parse_error", "The API returned a response that is not JSON.", 200);
  }
}

/** A short, user-facing sentence for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
