import { readFileSync } from "node:fs";
import type { Page, Route } from "@playwright/test";

/** A same-origin double of what the join page and the member portal call. Shapes follow the real server (see docs/portal.md). */
const fixture = <T>(name: string): T => JSON.parse(readFileSync(new URL(`../fixtures/portal/${name}.json`, import.meta.url), "utf8")) as T;

export const ORG = "11111111-1111-4111-8111-111111111111";
export const INVITATION = "3f2c1a9e-8b7d-4c6a-9e5f-0a1b2c3d4e5f";
export const CAPABILITY = "A".repeat(43);
export const PASSWORD = "a-long-enough-password";
export const MEMBER = { email: "newhire@acme.test", token: "m".repeat(43), name: "Nina Newhire" };
type Json = Record<string, unknown>;

export interface PortalWorld {
  /** Public branding by company code; an unknown code is a 404. */
  branding: Record<string, Json>;
  brandingDelayMs: number;
  /** How accepting an invitation answers for each capability. */
  invitations: Record<string, "valid" | "invalid" | "existing" | "outage">;
  /** The installer manifest the downloads mount serves; null is a 404. */
  manifest: Json | null;
  /** `usage/me`: null means this server has no such route (404). */
  usageMe: Json | null;
  roles: string[];
  /** The company admin view: members usage report rows. */
  members: Json[];
  departments: Json[];
  memberList: Json[];
  accepted: number;
  failAcceptOffline: boolean;
  /** The invitation preview: `null` is a server without the route; otherwise who each capability is for (any other capability is the uniform 404). */
  preview: Record<string, { account_email: string; display_name: string }> | "outage" | null;
}

export const newPortalWorld = (): PortalWorld => ({
  branding: { acme: fixture("branding-acme") },
  brandingDelayMs: 0,
  invitations: { [CAPABILITY]: "valid" },
  manifest: fixture("manifest"),
  usageMe: null,
  roles: ["member"],
  members: fixture<{ members: Json[] }>("usage-members").members,
  departments: [{ id: "d-legal", name: "Legal" }],
  memberList: [],
  accepted: 0,
  failAcceptOffline: false,
  preview: null,
});

const envelope = (code: string) => ({ error: { code, message: "Refused.", request_id: "00000000-0000-4000-8000-000000000000", retryable: false } });

export async function installPortal(page: Page, world: PortalWorld = newPortalWorld()) {
  const requests: Array<{ method: string; path: string; search: string; body: unknown; authorization: string | null }> = [];
  let chosenPassword = "";
  const reply = (route: Route, status: number, body?: unknown, extra: Record<string, string> = {}) =>
    route.fulfill({ status, contentType: "application/json", headers: extra, body: body === undefined ? "" : JSON.stringify(body) });

  await page.route("**/downloads/latest.json", (route) => (world.manifest ? reply(route, 200, world.manifest) : route.fulfill({ status: 404, body: "" })));
  await page.route("**/forge/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const body = request.postData() ? (request.postDataJSON() as Json) : undefined;
    const authorization = request.headers()["authorization"] ?? null;
    requests.push({ method, path, search: url.search, body, authorization });

    if (path === "/forge/v1/branding") {
      if (world.brandingDelayMs) await new Promise((resolve) => setTimeout(resolve, world.brandingDelayMs));
      const found = world.branding[url.searchParams.get("org") ?? ""];
      return found ? reply(route, 200, found) : reply(route, 404, envelope("NOT_FOUND"));
    }
    if (path === "/forge/v1/accounts/invitations/preview") {
      if (world.preview === null) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not Found" }) });
      if (world.preview === "outage") return reply(route, 503, envelope("SERVICE_UNAVAILABLE"));
      const found = world.preview[(body as { capability: string }).capability];
      return found ? reply(route, 200, found) : reply(route, 404, envelope("NOT_FOUND"));
    }
    if (path === "/forge/v1/accounts/invitations/accept") {
      const input = body as { capability: string; password: string };
      if (world.failAcceptOffline) return route.abort("failed");
      const kind = world.invitations[input.capability] ?? "invalid";
      if (kind === "outage") return reply(route, 503, envelope("SERVICE_UNAVAILABLE"));
      if (kind === "existing") return reply(route, 409, envelope("EXISTING_ACCOUNT_AUTH_REQUIRED"));
      if (kind === "invalid") return reply(route, 404, envelope("NOT_FOUND"));
      if (input.password.length < 15) return reply(route, 422, envelope("INVALID_REQUEST"));
      chosenPassword = input.password;
      world.accepted += 1;
      return reply(route, 201, { account_id: INVITATION, organization_id: ORG, membership_id: INVITATION, department_id: INVITATION });
    }
    if (path === "/forge/v1/accounts/login") {
      const login = body as { email: string; password: string };
      return login.email === MEMBER.email && login.password === chosenPassword
        ? reply(route, 200, { access_token: MEMBER.token, token_type: "Bearer", expires_at: "2099-01-01T00:00:00Z" })
        : reply(route, 401, envelope("UNAUTHENTICATED"));
    }
    if (authorization !== `Bearer ${MEMBER.token}`) return reply(route, 401, envelope("UNAUTHENTICATED"));
    if (path === "/forge/v1/platform/me") return reply(route, 403, envelope("PLATFORM_DENIED"));
    if (path === "/forge/v1/accounts/logout") return reply(route, 204);
    if (path === "/forge/v1/accounts/me") {
      return reply(route, 200, { account: { id: INVITATION, email: MEMBER.email, display_name: MEMBER.name }, organizations: [{ id: ORG, display_name: "Acme Corp", status: "active", roles: world.roles, departments: world.departments }] });
    }
    if (path === `/forge/v1/orgs/${ORG}/branding` && method === "GET") return reply(route, 200, { ...world.branding["acme"], code: "acme" });
    if (path === `/forge/v1/orgs/${ORG}/usage/me`) return world.usageMe ? reply(route, 200, world.usageMe) : reply(route, 404, envelope("NOT_FOUND"));
    if (path === `/forge/v1/orgs/${ORG}/usage/members`) {
      if (!world.roles.includes("organization_admin")) return reply(route, 404, envelope("NOT_FOUND"));
      return reply(route, 200, { members: world.members, next_after: null });
    }
    if (path === `/forge/v1/orgs/${ORG}/departments`) {
      if (method === "POST") {
        const created = { id: `d-${world.departments.length + 1}`, name: (body as { name: string }).name };
        if (world.departments.some((department) => department.name === created.name)) return reply(route, 409, envelope("CONFLICT"));
        world.departments.push(created);
        return reply(route, 201, created);
      }
      return reply(route, 200, { departments: world.departments });
    }
    if (path === `/forge/v1/orgs/${ORG}/members`) return reply(route, 200, { members: world.memberList });
    const assignment = path.match(new RegExp(`^/forge/v1/orgs/${ORG}/members/([^/]+)/department$`));
    if (assignment && method === "PUT") {
      const member = world.memberList.find((item) => item.id === assignment[1]);
      const department = world.departments.find((item) => item.id === (body as { department_id: string }).department_id);
      if (!world.roles.includes("organization_admin") || !member || !department) return reply(route, 404, envelope("NOT_FOUND"));
      member.departments = [department];
      return reply(route, 200, member);
    }
    return reply(route, 404, envelope("NOT_FOUND"));
  });
  return { requests, world };
}