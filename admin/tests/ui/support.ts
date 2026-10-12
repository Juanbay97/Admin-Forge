import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { test as base, type Page, type Route } from "@playwright/test";
import { build, preview } from "vite";
import { ADMIN_CSP } from "../csp";
import { contrastOfHex, generatePalette, type PaletteInput } from "../../src/brand/palette";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const PREVIEW_PORT = 3415;

export const ORG_A = "11111111-1111-4111-8111-111111111111";
export const ORG_B = "22222222-2222-4222-8222-222222222222";
/** The company code (slug) the real server returns on the authenticated branding read. */
export const ORG_CODES: Record<string, string> = { [ORG_A]: "org-a", [ORG_B]: "org-b" };
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
  catalogs?: Record<string, CatalogFixture>;
  /** Per-organisation branding; an organisation without one serves the Prometheon default at revision 0. */
  brandings?: Record<string, BrandingFixture>;
}

export interface BrandingFixture {
  revision: number;
  name: string;
  loginCopy: string;
  theme: { primary: string; accent: string; tint: string; heading: string; body: string };
  assets: Record<string, string>;
}

export const DEFAULT_BRANDING_FIXTURE: BrandingFixture = {
  revision: 0,
  name: "Prometheon Forge",
  loginCopy: "Sign in to your Forge workspace.",
  theme: { primary: "#0B1D26", accent: "#E07A2D", tint: "#E8DCC1", heading: "montserrat", body: "inter" },
  assets: {},
};

const BRANDING_FONTS = ["inter", "montserrat", "source-sans-3", "ibm-plex-sans", "nunito-sans", "roboto"];
const BRANDING_KINDS = ["logoLight", "logoDark", "isotipo"];
const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
// The server's own refusal messages (see forge.branding_api), so the page shows what a user would really see.
const BRANDING_MESSAGES: Record<string, string> = {
  color: "A color must be a #RRGGBB hex value.",
  font: "The font is not in the vetted list.",
  name: "The product name must be 1 to 40 plain characters.",
  contrast: "The primary color must reach 3:1 contrast against white.",
  unreadable:
    "These colors cannot produce a readable theme: the accent needs 3:1 contrast against white and the background tint must carry dark text.",
  unknownAsset: "The referenced logo was not uploaded for this organization.",
  type: "Only PNG and WebP images are accepted.",
  size: "The image is larger than the allowed size.",
};

export interface CatalogFixture {
  gatewayRevision: number;
  /** Models the gateway reports; null = no usable gateway, refresh fails. */
  upstream: string[] | null;
  revision: number;
  state: "CURRENT" | "UNPUBLISHED" | "STALE_GATEWAY";
  defaultModel: string | null;
  aliases: Record<string, string>;
  publications: unknown[];
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
  const brandings = backend.brandings ?? (backend.brandings = {});
  const uploads = new Map<string, Buffer>();
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
    const assetMatch = path.match(/^\/forge\/v1\/branding\/assets\/([0-9a-f]{64})$/);
    if (assetMatch) {
      // Public and content-addressed, but only for a logo some current revision references.
      const sha = assetMatch[1] ?? "";
      const referenced = Object.values(brandings).some((item) => Object.values(item.assets).includes(sha));
      const bytes = uploads.get(sha);
      if (!referenced || !bytes) return route.fulfill({ status: 404, body: "" });
      return route.fulfill({ status: 200, contentType: "image/png", body: bytes });
    }
    if (!account) return reply(route, 401, envelope("UNAUTHENTICATED", "Authentication is required."));
    if (path === "/forge/v1/accounts/logout") return reply(route, 204);
    const brandingMatch = path.match(/^\/forge\/v1\/orgs\/([^/]+)\/branding(\/reset|\/assets)?$/);
    if (brandingMatch) {
      const orgId = decodeURIComponent(brandingMatch[1] ?? "");
      await held.get(`branding:${orgId}`);
      if (!account.organizations.some((o) => o.id === orgId)) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
      const current = (brandings[orgId] ??= structuredClone(DEFAULT_BRANDING_FIXTURE));
      const view = () => ({
        revision: current.revision,
        name: current.name,
        loginCopy: current.loginCopy,
        theme: current.theme,
        assets: Object.fromEntries(Object.entries(current.assets).map(([kind, sha]) => [kind, `/forge/v1/branding/assets/${sha}`])),
      });
      const refuse = (key: string) => reply(route, 422, envelope("INVALID_REQUEST", BRANDING_MESSAGES[key] ?? ""));
      // Only the authenticated read carries the company code; save and reset answer without it.
      if (request.method() === "GET") return reply(route, 200, { ...view(), ...(ORG_CODES[orgId] ? { code: ORG_CODES[orgId] } : {}) });
      if (brandingMatch[2] === "/assets") {
        const kind = new URL(request.url()).searchParams.get("kind") ?? "";
        const bytes = request.postDataBuffer() ?? Buffer.alloc(0);
        if (!BRANDING_KINDS.includes(kind)) return refuse("type");
        if (!["image/png", "image/webp"].includes(request.headers()["content-type"] ?? "")) {
          return reply(route, 415, envelope("UNSUPPORTED_MEDIA_TYPE", BRANDING_MESSAGES.type ?? ""));
        }
        if (bytes.length > 262_144) return reply(route, 413, envelope("PAYLOAD_TOO_LARGE", BRANDING_MESSAGES.size ?? ""));
        const sha = createHash("sha256").update(bytes).digest("hex");
        uploads.set(sha, bytes);
        return reply(route, 201, {
          kind,
          sha256: sha,
          url: `/forge/v1/branding/assets/${sha}`,
          contentType: "image/png",
          width: bytes.readUInt32BE(16),
          height: bytes.readUInt32BE(20),
        });
      }
      const body = request.postDataJSON() as { expectedRevision: number; branding?: Omit<BrandingFixture, "revision"> };
      if (body.expectedRevision !== current.revision) {
        return reply(route, 409, envelope("REVISION_CONFLICT", "The branding revision changed."));
      }
      if (brandingMatch[2] === "/reset") {
        Object.assign(current, structuredClone({ ...DEFAULT_BRANDING_FIXTURE, revision: current.revision + 1 }));
        return reply(route, 200, view());
      }
      const next = body.branding;
      if (!next) return refuse("name");
      if (typeof next.name !== "string" || next.name.length < 1 || next.name.length > 40 || /[<>{}`\\]/.test(next.name)) return refuse("name");
      if (![next.theme.primary, next.theme.accent, next.theme.tint].every((color) => HEX_COLOR.test(color))) return refuse("color");
      if (!BRANDING_FONTS.includes(next.theme.heading) || !BRANDING_FONTS.includes(next.theme.body)) return refuse("font");
      if (contrastOfHex(next.theme.primary, "#FFFFFF") < 3) return refuse("contrast");
      if (!generatePalette(next.theme as PaletteInput)) return refuse("unreadable");
      if (Object.values(next.assets).some((sha) => !uploads.has(sha))) return refuse("unknownAsset");
      Object.assign(current, { revision: current.revision + 1, name: next.name, loginCopy: next.loginCopy, theme: next.theme, assets: next.assets });
      return reply(route, 200, view());
    }
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
    const scoped = path.match(
      /^\/forge\/v1\/orgs\/([^/]+)\/(departments|members|gateway\/catalogue\/status|gateway\/catalogue\/refresh|gateway|models\/publish|models)(?:\/([^/]+)\/(suspend|reactivate))?$/,
    );
    if (scoped) {
      const orgId = decodeURIComponent(scoped[1] ?? "");
      await held.get(orgId);
      const [, , collection, memberId, action] = scoped;
      if (collection === "departments") {
        const configured = backend.departments[orgId];
        if (!configured || configured.status !== 200) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
        return reply(route, 200, { departments: configured.items });
      }
      if (collection?.startsWith("gateway/catalogue") || collection?.startsWith("models")) {
        const catalog = backend.catalogs?.[orgId];
        if (!catalog) return reply(route, 404, envelope("NOT_FOUND", "Not found."));
        if (collection === "gateway/catalogue/status") {
          return reply(route, 200, {
            catalogue_revision: catalog.revision,
            default_model: catalog.defaultModel,
            publication_state: catalog.state,
          });
        }
        if (collection === "gateway/catalogue/refresh") {
          if (!catalog.upstream) return reply(route, 503, envelope("SERVICE_UNAVAILABLE", "Unavailable."));
          return reply(route, 200, {
            gateway_revision: catalog.gatewayRevision,
            model_ids: catalog.upstream,
            capability_state: "unknown",
            verification: "unverified",
          });
        }
        if (collection === "models") {
          if (catalog.state === "UNPUBLISHED") return reply(route, 404, envelope("NOT_FOUND", "Not found."));
          return reply(route, 200, {
            organization_id: orgId,
            revision: catalog.revision,
            default_model: catalog.defaultModel,
            models: Object.keys(catalog.aliases).sort().map((id) => ({ id })),
          });
        }
        const body = request.postDataJSON() as {
          expected_catalogue_revision: number;
          expected_gateway_revision: number;
          aliases: Record<string, string>;
          default_alias: string;
        };
        catalog.publications.push(body);
        if (body.expected_catalogue_revision !== catalog.revision || body.expected_gateway_revision !== catalog.gatewayRevision) {
          return reply(route, 409, envelope("REVISION_CONFLICT", "Revision changed."));
        }
        const valid = Object.entries(body.aliases).every(
          ([alias, id]) => /^[a-z][a-z0-9_-]{0,63}$/.test(alias) && catalog.upstream?.includes(id),
        );
        if (!valid || !(body.default_alias in body.aliases)) return reply(route, 422, envelope("INVALID_REQUEST", "Invalid."));
        Object.assign(catalog, {
          revision: catalog.revision + 1,
          state: "CURRENT",
          defaultModel: body.default_alias,
          aliases: body.aliases,
        });
        return reply(route, 200, { revision: catalog.revision, default_model: body.default_alias, models: Object.keys(body.aliases).sort() });
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
    catalog: (orgId: string) => backend.catalogs?.[orgId],
    /** The branding the double currently serves for an organisation. */
    branding: (orgId: string) => brandings[orgId],
    /** Another administrator saves branding behind this page's back. */
    bumpBranding(orgId: string) {
      const current = (brandings[orgId] ??= structuredClone(DEFAULT_BRANDING_FIXTURE));
      current.revision += 1;
      current.name = "Changed Elsewhere";
    },
    /** Delay every branding reply for one organisation until `releaseBranding` is called. */
    holdBranding(orgId: string) {
      held.set(`branding:${orgId}`, new Promise<void>((resolve) => release.set(`branding:${orgId}`, resolve)));
    },
    releaseBranding(orgId: string) {
      release.get(`branding:${orgId}`)?.();
    },
    /** The gateway or catalogue moves on after the page refreshed discovery. */
    bumpCatalog(orgId: string) {
      const catalog = backend.catalogs?.[orgId];
      if (catalog) catalog.gatewayRevision += 1;
    },
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
  catalogs: {
    [ORG_A]: {
      gatewayRevision: 3,
      upstream: ["gpt-4o", "gpt-4o-mini", "4o-realtime"],
      revision: 0,
      state: "UNPUBLISHED",
      defaultModel: null,
      aliases: {},
      publications: [],
    },
    [ORG_B]: {
      gatewayRevision: 5,
      upstream: ["claude-3-5-sonnet"],
      revision: 2,
      state: "CURRENT",
      defaultModel: "deep",
      aliases: { deep: "claude-3-5-sonnet", quick: "claude-3-5-sonnet" },
      publications: [],
    },
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
