import { readFileSync } from "node:fs";
import type { Page, Route } from "@playwright/test";

const fixture = <T>(name: string): T => JSON.parse(readFileSync(new URL(`../fixtures/platform/${name}.json`, import.meta.url), "utf8")) as T;

export const OWNER = { email: "owner@platform.test", password: "owner-password-123", token: "t".repeat(43) };
export const GOOD_CODE = "123456";
export const RECOVERY = "aaaa-bbbb-cccc";
export const ACME = "11111111-1111-4111-8111-111111111111";
export const GLOBEX = "22222222-2222-4222-8222-222222222222";

type Json = Record<string, unknown>;
export interface Company { id: string; slug: string; display_name: string; active: boolean }

/** A same-origin double of the hidden platform API with the real response shapes (tests/fixtures/platform). */
export interface World {
  mfa: { state: "none" | "pending" | "active"; verified: boolean };
  companies: Company[];
  audit: Json[];
  keys: Json[];
  assignments: Record<string, Json[]>;
  models: Record<string, string[]>;
  prices: Json[];
  branding: Record<string, Json>;
  /** Fail these `METHOD /path-suffix` requests once with the given status/code. */
  failOnce: Record<string, { status: number; code: string }>;
  /** Usage windows by route. */
  usage: { totals: Json; companies: Json; models: Json };
}

export const newWorld = (): World => ({
  mfa: { state: "active", verified: false },
  companies: fixture<{ companies: Company[] }>("companies").companies.map((company) => ({ ...company })),
  audit: fixture<{ entries: Json[] }>("audit").entries,
  keys: fixture<{ keys: Json[] }>("gateway-keys").keys,
  assignments: { [ACME]: fixture<{ keys: Json[] }>("company-keys").keys },
  models: { [ACME]: ["gpt-4o", "gpt-4o-mini"] },
  prices: fixture<{ prices: Json[] }>("prices").prices,
  branding: {},
  failOnce: {},
  usage: { totals: fixture("usage-totals"), companies: fixture("usage-companies"), models: fixture("usage-models") },
});

const envelope = (code: string, message = "Refused.") => ({ error: { code, message, request_id: "00000000-0000-4000-8000-000000000000", retryable: false } });

export async function installPlatform(page: Page, world: World = newWorld()) {
  const requests: Array<{ method: string; path: string; search: string; body: unknown }> = [];
  const reply = (route: Route, status: number, body?: unknown) =>
    route.fulfill({ status, contentType: "application/json", body: body === undefined ? "" : JSON.stringify(body) });

  await page.route("**/forge/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const body = request.postData() ? (request.postDataJSON() as Json) : undefined;
    requests.push({ method, path, search: url.search, body });
    if (path === "/forge/v1/accounts/login") {
      const login = body as { email: string; password: string };
      return login.email === OWNER.email && login.password === OWNER.password
        ? reply(route, 200, { access_token: OWNER.token, token_type: "Bearer", expires_at: "2099-01-01T00:00:00Z" })
        : reply(route, 401, envelope("UNAUTHENTICATED"));
    }
    if (request.headers()["authorization"] !== `Bearer ${OWNER.token}`) return reply(route, 401, envelope("UNAUTHENTICATED"));
    if (path === "/forge/v1/accounts/logout") return reply(route, 204);
    if (path === "/forge/v1/accounts/me") return reply(route, 200, { account: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", email: OWNER.email, display_name: "Platform Owner" }, organizations: [] });
    const key = `${method} ${path.replace("/forge/v1/platform", "")}`;
    const failure = Object.keys(world.failOnce).find((pattern) => key.startsWith(pattern));
    if (failure) {
      const { status, code } = world.failOnce[failure]!;
      delete world.failOnce[failure];
      return reply(route, status, envelope(code));
    }
    if (key === "GET /me") return reply(route, 200, { account_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", role: "platform_owner", mfa: { ...world.mfa, fresh: world.mfa.verified } });
    if (key === "POST /mfa/enroll") {
      if (world.mfa.state === "active") return reply(route, 409, envelope("MFA_ENROLLED"));
      world.mfa = { state: "pending", verified: false };
      return reply(route, 201, fixture("enrollment"));
    }
    if (key === "POST /login/mfa") {
      const factor = body as { code?: string; recovery_code?: string };
      if (factor.code === GOOD_CODE || factor.recovery_code === RECOVERY) {
        world.mfa = { state: "active", verified: true };
        return reply(route, 200, { verified: true });
      }
      return reply(route, 403, envelope("MFA_INVALID"));
    }
    // Everything below needs a verified second factor, exactly like the server.
    if (!world.mfa.verified) return reply(route, 403, envelope("MFA_REQUIRED"));
    const handled = await handlers(key, url, body, world, reply, route);
    return handled ?? reply(route, 404, envelope("NOT_FOUND"));
  });
  return { requests, world };
}

type Reply = (route: Route, status: number, body?: unknown) => Promise<void>;
async function handlers(key: string, url: URL, body: Json | undefined, world: World, reply: Reply, route: Route): Promise<void | null> {
  let match: RegExpMatchArray | null;
  if (key === "GET /companies") return reply(route, 200, { companies: world.companies, next_after: null });
  if (key === "GET /audit") return reply(route, 200, { entries: world.audit, next_before: null });
  if (key === "GET /gateway-keys") return reply(route, 200, { keys: world.keys, allowed_origins: ["https://gateway.example.test"] });
  if (key === "GET /prices") return reply(route, 200, { prices: world.prices });
  if (key === "GET /usage/totals") return reply(route, 200, world.usage.totals);
  if (key === "GET /usage/companies") return reply(route, 200, world.usage.companies);
  if (key === "GET /usage/models") return reply(route, 200, world.usage.models);
  if ((match = key.match(/^GET \/companies\/([^/]+)$/))) {
    const found = world.companies.find((company) => company.id === match![1]);
    return found ? reply(route, 200, found) : reply(route, 404, envelope("NOT_FOUND"));
  }
  if ((match = key.match(/^POST \/companies\/([^/]+)\/(suspend|reactivate)$/))) {
    const found = world.companies.find((company) => company.id === match![1]);
    if (!found) return reply(route, 404, envelope("NOT_FOUND"));
    found.active = match[2] === "reactivate";
    return reply(route, 200, found);
  }
  return null;
}