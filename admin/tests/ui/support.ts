import { fileURLToPath } from "node:url";
import { test as base, type Page, type Route } from "@playwright/test";
import { build, preview } from "vite";
import { ADMIN_CSP } from "../csp";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const PREVIEW_PORT = 3415;

export const ORG_A = "11111111-1111-4111-8111-111111111111";
export const ORG_B = "22222222-2222-4222-8222-222222222222";
export const PROD = "https://ia.prometheonlab.com";
export const LOCAL = "http://127.0.0.1:3413";
export const ORG_C = "33333333-3333-4333-8333-333333333333";

export interface Account {
  password: string;
  token: string;
  organizations: Array<{ id: string; name: string; roles: string[] }>;
}

export interface Department {
  id: string;
  name: string;
}

export interface Member {
  id: string;
  email: string;
  display_name: string;
  status: "active" | "suspended";
  roles: string[];
  departments: Department[];
}

export interface GatewayFixture {
  status: "NOT_CONFIGURED" | "SAVED_UNVERIFIED";
  revision: number;
  endpoint: string;
  allowed_endpoints: string[];
  savedKey?: string;
}

export interface Backend {
  accounts: Record<string, Account>;
  departments: Record<string, { status: number; items: Department[] }>;
  members?: Record<string, Member[]>;
  gateways?: Record<string, GatewayFixture>;
}

export interface RecordedRequest {
  method: string;
  path: string;
  authorization: string | null;
}

const envelope = (code: string, message: string) => ({
  error: { code, message, request_id: "00000000-0000-4000-8000-000000000000", retryable: false },
});

/** A same-origin /forge/v1 double that records requests and can hold an organisation's replies. */
export async function installBackend(page: Page, source: Backend) {
  const backend = structuredClone(source); // members mutate; never leak between tests
  const requests: RecordedRequest[] = [];
  const invitations: unknown[] = [];
  const held = new Map<string, Promise<void>>();
  const release = new Map<string, () => void>();

  const reply = (route: Route, status: number, body?: unknown) =>
    route.fulfill({
      status,
      contentType: "application/json",
      body: body === undefined ? "" : JSON.stringify(body),
    });

  await page.route("**/forge/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const authorization = request.headers()["authorization"] ?? null;
    requests.push({ method: request.method(), path, authorization });
    const account = Object.values(backend.accounts).find((a) => `Bearer ${a.token}` === authorization);

    if (path === "/forge/v1/accounts/login") {
      const body = request.postDataJSON() as { email: string; password: string };
      const found = backend.accounts[body.email];
      if (!found || found.password !== body.password) {
        return reply(route, 401, envelope("UNAUTHENTICATED", "Invalid credentials."));
      }
      return reply(route, 200, { access_token: found.token, expires_at: "2099-01-01T00:00:00Z", token_type: "Bearer" });
    }
    if (!account) return reply(route, 401, envelope("UNAUTHENTICATED", "Authentication is required."));
    if (path === "/forge/v1/accounts/logout") return reply(route, 204);
    if (path === "/forge/v1/accounts/me") {
      return reply(route, 200, {
        account: { id: "acc-1", email: "admin@example.com", display_name: "Alex Admin" },
        organizations: account.organizations.map((o) => ({
          id: o.id,
          display_name: o.name,
          status: "active",
          roles: o.roles,
          departments: [],
        })),
      });
    }
    if (path === "/forge/v1/accounts/invitations") {
      const body = request.postDataJSON() as { email: string };
      invitations.push(body);
      if (body.email === "invalid@example.com") return reply(route, 422, envelope("INVALID_REQUEST", "Invalid."));
      return reply(route, 201, {
        invitation_id: "inv-1",
        expires_at: "2099-01-01T00:00:00Z",
        delivery_state: "pending",
        delivery_channel: "local_mailbox",
      });
    }
    const scoped = path.match(/^\/forge\/v1\/orgs\/([^/]+)\/(departments|members|gateway)(?:\/([^/]+)\/(suspend|reactivate))?$/);
    if (scoped) {
      const orgId = decodeURIComponent(scoped[1] ?? "");
      await held.get(orgId);
      const [, , collection, memberId, action] = scoped;
      if (collection === "departments") {
        const configured = backend.departments[orgId];
        if (!configured || configured.status !== 200) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
        return reply(route, 200, { departments: configured.items });
      }
      if (collection === "gateway") {
        const gateway = backend.gateways?.[orgId];
        if (!gateway) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
        if (request.method() === "GET") return reply(route, 200, withoutKey(gateway));
        const body = request.postDataJSON() as { expected_revision: number; api_key: string; endpoint: string };
        if (body.expected_revision !== gateway.revision) {
          return reply(route, 409, envelope("REVISION_CONFLICT", "Gateway configuration revision changed."));
        }
        if (!gateway.allowed_endpoints.includes(body.endpoint) || body.api_key === "rejected-key") {
          return reply(route, 422, envelope("INVALID_REQUEST", "Invalid."));
        }
        Object.assign(gateway, {
          status: "SAVED_UNVERIFIED",
          revision: gateway.revision + 1,
          endpoint: body.endpoint,
          savedKey: body.api_key,
        });
        return reply(route, 200, { status: gateway.status, revision: gateway.revision, endpoint: gateway.endpoint });
      }
      const members = backend.members?.[orgId];
      if (!members) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
      if (!action) return reply(route, 200, { members });
      const target = members.find((m) => m.id === memberId);
      if (!target) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
      const otherAdmins = members.filter(
        (m) => m !== target && m.status === "active" && m.roles.includes("organization_admin"),
      );
      if (action === "suspend" && target.roles.includes("organization_admin") && otherAdmins.length === 0) {
        return reply(route, 409, envelope("LAST_ADMIN", "The last administrator cannot be suspended."));
      }
      target.status = action === "suspend" ? "suspended" : "active";
      return reply(route, 200, target);
    }
    return reply(route, 404, envelope("NOT_FOUND", "Not found."));
  });

  return {
    requests,
    invitations,
    /** What the double stored for an organisation, key included (it is never sent back). */
    stored: (orgId: string) => backend.gateways?.[orgId],
    /** Another administrator changes the gateway behind this page's back. */
    bumpGateway(orgId: string) {
      const gateway = backend.gateways?.[orgId];
      if (gateway) gateway.revision += 1;
    },
    /** Delay every reply for one organisation until `letThrough` is called. */
    hold(orgId: string) {
      held.set(orgId, new Promise<void>((resolve) => release.set(orgId, resolve)));
    },
    letThrough(orgId: string) {
      release.get(orgId)?.();
    },
  };
}

/** The read model never carries the key. */
function withoutKey({ savedKey: _savedKey, ...visible }: GatewayFixture) {
  return visible;
}

function member(id: string, email: string, name: string, roles: string[], department: Department): Member {
  return { id, email, display_name: name, status: "active", roles, departments: [department] };
}

export const ADMIN_BACKEND: Backend = {
  accounts: {
    "admin@example.com": {
      password: "correct-horse-battery",
      token: "token-admin-secret",
      organizations: [{ id: ORG_A, name: "Org A", roles: ["organization_admin"] }],
    },
    "multi@example.com": {
      password: "correct-horse-battery",
      token: "token-multi-secret",
      organizations: [
        { id: ORG_A, name: "Org A", roles: ["organization_admin"] },
        { id: ORG_B, name: "Org B", roles: ["organization_admin", "member"] },
        { id: ORG_C, name: "Org C", roles: ["member"] },
      ],
    },
    "member@example.com": {
      password: "correct-horse-battery",
      token: "token-member-secret",
      organizations: [{ id: ORG_A, name: "Org A", roles: ["member"] }],
    },
  },
  departments: {
    [ORG_A]: { status: 200, items: [{ id: "d-legal", name: "Legal" }] },
    [ORG_B]: { status: 200, items: [{ id: "d-finance", name: "Finance" }] },
  },
  gateways: {
    [ORG_A]: { status: "NOT_CONFIGURED", revision: 0, endpoint: PROD, allowed_endpoints: [PROD, LOCAL] },
    [ORG_B]: { status: "SAVED_UNVERIFIED", revision: 2, endpoint: LOCAL, allowed_endpoints: [PROD, LOCAL] },
  },
  members: {
    [ORG_A]: [
      member("m-alex", "alex@example.com", "Alex Admin", ["organization_admin"], { id: "d-legal", name: "Legal" }),
      member("m-pat", "pat@example.com", "Pat Member", ["member"], { id: "d-legal", name: "Legal" }),
    ],
    [ORG_B]: [
      member("m-bea", "bea@example.com", "Bea Banker", ["organization_admin"], { id: "d-finance", name: "Finance" }),
      member("m-cy", "cy@example.com", "Cy Clerk", ["member"], { id: "d-finance", name: "Finance" }),
    ],
  },
};

export const test = base.extend<{ adminUrl: string }, { origin: string }>({
  // The production bundle, built once per run into an ignored directory and served with
  // the same CSP the control plane sends.
  origin: [
    async ({}, use) => {
      await build({ root: ROOT, logLevel: "warn", build: { outDir: ".test-dist", emptyOutDir: true } });
      const server = await preview({
        root: ROOT,
        build: { outDir: ".test-dist" },
        preview: {
          host: "127.0.0.1",
          port: PREVIEW_PORT,
          strictPort: true,
          headers: { "Content-Security-Policy": ADMIN_CSP },
        },
      });
      await use(`http://127.0.0.1:${PREVIEW_PORT}`);
      await server.close();
    },
    { scope: "worker" },
  ],
  adminUrl: async ({ origin }, use) => use(`${origin}/admin/`),
});

export { expect } from "@playwright/test";
