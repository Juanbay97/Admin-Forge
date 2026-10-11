import { fileURLToPath } from "node:url";
import { test as base, type Page, type Route } from "@playwright/test";
import { build, preview } from "vite";
import { ADMIN_CSP } from "../csp";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const PREVIEW_PORT = 3415;

export const ORG_A = "11111111-1111-4111-8111-111111111111";
export const ORG_B = "22222222-2222-4222-8222-222222222222";
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

export interface Backend {
  accounts: Record<string, Account>;
  departments: Record<string, { status: number; items: Department[] }>;
}

export interface RecordedRequest {
  method: string;
  path: string;
  authorization: string | null;
}

const envelope = (code: string, message: string) => ({
  error: { code, message, request_id: "00000000-0000-4000-8000-000000000000", retryable: false },
});

/** A same-origin /forge/v1 double that records requests and can hold a department reply. */
export async function installBackend(page: Page, backend: Backend) {
  const requests: RecordedRequest[] = [];
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
    const departments = path.match(/^\/forge\/v1\/orgs\/([^/]+)\/departments$/);
    if (departments) {
      const orgId = decodeURIComponent(departments[1] ?? "");
      await held.get(orgId);
      const configured = backend.departments[orgId];
      if (!configured || configured.status !== 200) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
      return reply(route, 200, { departments: configured.items });
    }
    return reply(route, 404, envelope("NOT_FOUND", "Not found."));
  });

  return {
    requests,
    /** Delay the department reply of one organisation until `letThrough` is called. */
    hold(orgId: string) {
      held.set(orgId, new Promise<void>((resolve) => release.set(orgId, resolve)));
    },
    letThrough(orgId: string) {
      release.get(orgId)?.();
    },
  };
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
