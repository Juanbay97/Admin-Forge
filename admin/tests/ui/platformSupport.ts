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
  failOnce: Record<string, { status: number; code: string; times?: number }>;
  /** Usage windows by route. */
  usage: { totals: Json; companies: Json; models: Json };
}

const DEFAULT_BRANDING: Json = fixture("branding-default");

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
    if (path === "/forge/v1/accounts/password-reset/consume") {
      const reset = body as { capability: string; password: string };
      if (reset.capability !== "A".repeat(43)) return reply(route, 404, envelope("NOT_FOUND"));
      return reset.password.length < 15 ? reply(route, 422, envelope("INVALID_REQUEST")) : reply(route, 204);
    }
    if (request.headers()["authorization"] !== `Bearer ${OWNER.token}`) return reply(route, 401, envelope("UNAUTHENTICATED"));
    if (path === "/forge/v1/accounts/logout") return reply(route, 204);
    // A platform owner has no membership, so the real directory answers accounts/me with 404.
    if (path === "/forge/v1/accounts/me") return reply(route, 404, envelope("NOT_FOUND"));
    const key = `${method} ${path.replace("/forge/v1/platform", "")}`;
    const failure = Object.keys(world.failOnce).find((pattern) => key.startsWith(pattern));
    if (failure) {
      const { status, code, times = 1 } = world.failOnce[failure]!;
      if (times <= 1) delete world.failOnce[failure];
      else world.failOnce[failure] = { status, code, times: times - 1 };
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
    const sent: Reply = async (target, status, payload) => {
      await reply(target, status, payload);
      return true;
    };
    return (await handlers(key, url, body, world, sent, route)) || reply(route, 404, envelope("NOT_FOUND"));
  });
  return { requests, world };
}

type Reply = (route: Route, status: number, body?: unknown) => Promise<boolean>;
async function handlers(key: string, _url: URL, body: Json | undefined, world: World, reply: Reply, route: Route): Promise<boolean> {
  let match: RegExpMatchArray | null;
  if (key === "GET /companies") return reply(route, 200, { companies: world.companies, next_after: null });
  if (key === "GET /audit") return reply(route, 200, { entries: world.audit, next_before: null });
  if (key === "GET /gateway-keys") return reply(route, 200, { keys: world.keys, allowed_origins: ["https://gateway.example.test"] });
  if (key === "GET /prices") return reply(route, 200, { prices: world.prices });
  if (key === "GET /usage/totals") return reply(route, 200, world.usage.totals);
  if (key === "GET /usage/companies") return reply(route, 200, world.usage.companies);
  if (key === "GET /usage/models") return reply(route, 200, world.usage.models);
  if (key === "POST /companies") {
    const input = body as { slug: string; display_name: string };
    if (world.companies.some((company) => company.slug === input.slug)) return reply(route, 409, envelope("COMPANY_CONFLICT"));
    const created = { id: `99999999-9999-4999-8999-${String(world.companies.length + 1).padStart(12, "0")}`, slug: input.slug, display_name: input.display_name, active: true };
    world.companies.push(created);
    return reply(route, 201, { ...created, invitation: { id: "44444444-4444-4444-8444-444444444444", expires_at: "2026-10-20T12:00:00+00:00", delivery_state: "delivered", delivery_channel: "local_mailbox" } });
  }
  if ((match = key.match(/^(GET|PUT|POST) \/companies\/([^/]+)\/(branding|gateway-keys|model-access|branding\/reset)$/))) {
    const [, method, id, what] = match as unknown as [string, string, string, string];
    if (!world.companies.some((company) => company.id === id)) return reply(route, 404, envelope("NOT_FOUND"));
    if (what === "gateway-keys") {
      if (method === "PUT") {
        const entries = (body as { keys: Array<{ key_id: string; priority: number; active: boolean }> }).keys;
        world.assignments[id] = entries.map((entry) => {
          const known = world.keys.find((item) => item.id === entry.key_id) ?? {};
          return { key_id: entry.key_id, label: known.label ?? "Key", origin: known.origin ?? "https://gateway.example.test", priority: entry.priority, active: entry.active, key_status: "active", has_key: true };
        });
      }
      return reply(route, 200, { keys: world.assignments[id] ?? [] });
    }
    if (what === "model-access") {
      if (method === "PUT") world.models[id] = (body as { models: string[] }).models;
      return reply(route, 200, { models: world.models[id] ?? [] });
    }
    const current = (world.branding[id] ??= { ...DEFAULT_BRANDING });
    if (what === "branding/reset") world.branding[id] = { ...DEFAULT_BRANDING, revision: (current.revision as number) + 1 };
    if (method === "PUT") {
      const change = body as { expectedRevision: number; branding: Json };
      if (change.expectedRevision !== current.revision) return reply(route, 409, envelope("REVISION_CONFLICT"));
      world.branding[id] = { ...change.branding, revision: (current.revision as number) + 1, assets: {} };
    }
    return reply(route, 200, world.branding[id]);
  }
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
  return false;
}