import type { ErrorEnvelope } from "@/types/api";

// Single API base. In dev, Vite proxies /api to the backend; in the container
// the same relative path is served. There is no other origin.
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiRequestError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

/** Typed fetch that unwraps the backend's {error:{code,message}} envelope. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed with ${res.status}`;
    try {
      const body = (await res.json()) as ErrorEnvelope;
      if (body?.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // Non-JSON error body; keep the defaults.
    }
    throw new ApiRequestError(code, message, res.status);
  }

  return (await res.json()) as T;
}
