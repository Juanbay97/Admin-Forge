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

/** The real client; pages that only read and write JSON depend on the narrower `ApiClient`. */
export interface UploadClient extends ApiClient, DownloadClient {
  /** POST raw bytes (an image) with an explicit media type instead of JSON. */
  upload<T = unknown>(path: string, body: Blob | Uint8Array, contentType: string): Promise<T>;
}

/** An authenticated binary GET (the company-stamped installer): the bytes and the raw `Content-Disposition` header, unvalidated. */
export interface DownloadClient {
  download(path: string): Promise<{ blob: Blob; disposition: string | null }>;
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
export function createApiClient({ session, fetchImpl = (...args) => fetch(...args) }: ClientOptions): UploadClient {
  async function perform(method: string, path: string, headers: Headers, body?: BodyInit): Promise<Response> {
    const token = session.token();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    let response: Response;
    try {
      response = await fetchImpl(path, {
        method,
        headers,
        body,
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
    return response;
  }

  async function send<T>(method: string, path: string, headers: Headers, body?: BodyInit): Promise<T> {
    const response = await perform(method, path, headers, body);
    return (response.status === 204 ? undefined : await response.json()) as T;
  }

  return {
    async download(path: string) {
      const response = await perform("GET", path, new Headers());
      return { blob: await response.blob(), disposition: response.headers.get("Content-Disposition") };
    },
    request<T>(method: string, path: string, body?: unknown): Promise<T> {
      const headers = new Headers();
      if (body !== undefined) headers.set("Content-Type", "application/json");
      return send<T>(method, path, headers, body === undefined ? undefined : JSON.stringify(body));
    },
    upload<T>(path: string, body: Blob | Uint8Array, contentType: string): Promise<T> {
      return send<T>("POST", path, new Headers({ "Content-Type": contentType }), body as BodyInit);
    },
  };
}