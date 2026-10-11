import type { Session } from "../auth/session";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClient {
  request<T = unknown>(method: string, path: string, body?: unknown): Promise<T>;
}

interface ClientOptions {
  session: Session;
  fetchImpl?: typeof fetch;
}

function errorFrom(status: number, text: string): ApiError {
  try {
    const detail = (JSON.parse(text) as { error?: { code?: unknown; message?: unknown } }).error;
    if (typeof detail?.code === "string" && typeof detail.message === "string") {
      return new ApiError(status, detail.code, detail.message);
    }
  } catch {
    // Not a JSON envelope: fall through to the generic status-only error.
  }
  return new ApiError(status, "UNKNOWN", `Request failed (${status}).`);
}

/** Same-origin JSON client: bearer auth, no cookies, no referrer, typed errors. */
export function createApiClient({ session, fetchImpl = (...args) => fetch(...args) }: ClientOptions): ApiClient {
  return {
    async request<T>(method: string, path: string, body?: unknown): Promise<T> {
      const token = session.token();
      const headers = new Headers();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (body !== undefined) headers.set("Content-Type", "application/json");

      let response: Response;
      try {
        response = await fetchImpl(path, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          credentials: "omit",
          referrerPolicy: "no-referrer",
        });
      } catch {
        throw new ApiError(0, "NETWORK", "The server could not be reached.");
      }
      if (!response.ok) {
        // An expired or revoked session must not linger in memory.
        if (response.status === 401 && token) session.clear();
        throw errorFrom(response.status, await response.text());
      }
      return (response.status === 204 ? undefined : await response.json()) as T;
    },
  };
}