import { expect, test } from "@playwright/test";
import { createAccountApi } from "../../src/api/account";
import { ApiError, createApiClient } from "../../src/api/client";
import { createSession } from "../../src/auth/session";

type Call = { url: string; init: RequestInit };

function stub(respond: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init: RequestInit = {}) => {
    const call = { url, init };
    calls.push(call);
    return respond(call);
  }) as unknown as typeof fetch;
  return { calls, fetchImpl };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function authed(respond: (call: Call) => Response | Promise<Response>) {
  const session = createSession();
  session.set("secret-token");
  const { calls, fetchImpl } = stub(respond);
  return { session, calls, client: createApiClient({ session, fetchImpl }) };
}

test.describe("api client", () => {
  test("sends the bearer token and parses JSON", async () => {
    const { client, calls } = authed(() => json(200, { ok: 1 }));
    expect(await client.request("GET", "/forge/v1/accounts/me")).toEqual({ ok: 1 });
    expect(calls[0]?.url).toBe("/forge/v1/accounts/me");
    expect(new Headers(calls[0]?.init.headers).get("Authorization")).toBe("Bearer secret-token");
  });

  test("sends no authorization header without a session", async () => {
    const { fetchImpl, calls } = stub(() => json(200, {}));
    const client = createApiClient({ session: createSession(), fetchImpl });
    await client.request("POST", "/forge/v1/accounts/login", { email: "a@b.co" });
    const headers = new Headers(calls[0]?.init.headers);
    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(calls[0]?.init.body).toBe('{"email":"a@b.co"}');
  });

  test("never lets the browser keep credentials or referrers", async () => {
    const { client, calls } = authed(() => json(200, {}));
    await client.request("GET", "/forge/v1/accounts/me");
    expect(calls[0]?.init.credentials).toBe("omit");
    expect(calls[0]?.init.referrerPolicy).toBe("no-referrer");
  });

  test("an empty 204 resolves to undefined", async () => {
    const { client } = authed(() => new Response(null, { status: 204 }));
    expect(await client.request("POST", "/forge/v1/accounts/logout")).toBeUndefined();
  });

  test("maps the error envelope to a typed ApiError", async () => {
    const { client } = authed(() => json(409, { error: { code: "REVISION_CONFLICT", message: "stale", request_id: "r1" } }));
    const error = await client.request("PUT", "/x", {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "REVISION_CONFLICT", message: "stale" });
  });

  test("an unreadable error body still yields a status-only error", async () => {
    const { client } = authed(() => new Response("<html>bad gateway</html>", { status: 502 }));
    const error = await client.request("GET", "/x").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 502, code: "UNKNOWN" });
  });

  test("a network failure becomes a status-0 error", async () => {
    const session = createSession();
    const client = createApiClient({ session, fetchImpl: (async () => { throw new TypeError("offline"); }) as unknown as typeof fetch });
    expect(await client.request("GET", "/x").catch((e: unknown) => e)).toMatchObject({ status: 0, code: "NETWORK" });
  });

  test("a 401 on an authenticated call ends the session", async () => {
    const { client, session } = authed(() => json(401, { error: { code: "UNAUTHENTICATED", message: "no" } }));
    await client.request("GET", "/forge/v1/accounts/me").catch(() => undefined);
    expect(session.token()).toBeNull();
  });

  test("other failures keep the session", async () => {
    const { client, session } = authed(() => json(404, { error: { code: "NOT_FOUND", message: "no" } }));
    await client.request("GET", "/x").catch(() => undefined);
    expect(session.token()).toBe("secret-token");
  });

  test("upload sends raw bytes with the given media type and the bearer token, not JSON", async () => {
    const { client, calls } = authed(() => json(201, { ok: 1 }));
    const bytes = new Uint8Array([137, 80, 78, 71]);
    expect(await client.upload("/forge/v1/x/assets?kind=isotipo", bytes, "image/png")).toEqual({ ok: 1 });
    const headers = new Headers(calls[0]?.init.headers);
    expect(calls[0]?.init.method).toBe("POST");
    expect(headers.get("Content-Type")).toBe("image/png");
    expect(headers.get("Authorization")).toBe("Bearer secret-token");
    expect(calls[0]?.init.body).toBe(bytes);
    expect(calls[0]?.init.credentials).toBe("omit");
  });

  test("upload errors map to the same typed ApiError", async () => {
    const { client } = authed(() => json(415, { error: { code: "UNSUPPORTED_MEDIA_TYPE", message: "Only PNG and WebP images are accepted." } }));
    const error = await client.upload("/x", new Uint8Array(1), "image/svg+xml").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 415, code: "UNSUPPORTED_MEDIA_TYPE", message: "Only PNG and WebP images are accepted." });
  });
});

test.describe("account api", () => {
  test("login posts the credentials and returns the token without storing it", async () => {
    const session = createSession();
    const { fetchImpl, calls } = stub(() => json(200, { access_token: "tok", expires_at: "later", token_type: "Bearer" }));
    const api = createAccountApi(createApiClient({ session, fetchImpl }));
    expect(await api.login("a@example.com", "a-long-enough-pass")).toBe("tok");
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ email: "a@example.com", password: "a-long-enough-pass" });
    expect(session.token()).toBeNull();
  });

  test("requestReset posts only the email and resolves for the neutral 202", async () => {
    const { fetchImpl, calls } = stub(() => json(202, { status: "accepted", delivery_channel: "smtp" }));
    const api = createAccountApi(createApiClient({ session: createSession(), fetchImpl }));
    await api.requestReset("a@example.com");
    expect(calls[0]?.url).toBe("/forge/v1/accounts/password-reset/request");
    expect(calls[0]?.init.method).toBe("POST");
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ email: "a@example.com" });
  });

  test("me, departments and logout use the contract paths", async () => {
    const session = createSession();
    session.set("tok");
    const { fetchImpl, calls } = stub(({ url }) =>
      url.endsWith("/logout") ? new Response(null, { status: 204 }) : json(200, { departments: [{ id: "d", name: "Legal" }], account: {}, organizations: [] }),
    );
    const api = createAccountApi(createApiClient({ session, fetchImpl }));
    await api.me();
    expect(await api.departments("org/with space")).toEqual([{ id: "d", name: "Legal" }]);
    await api.logout();
    expect(calls.map((c) => `${c.init.method} ${c.url}`)).toEqual([
      "GET /forge/v1/accounts/me",
      "GET /forge/v1/orgs/org%2Fwith%20space/departments",
      "POST /forge/v1/accounts/logout",
    ]);
  });
});
