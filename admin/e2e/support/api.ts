import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, type APIRequestContext } from "@playwright/test";

// Direct API calls the journeys use to arrange real state on the stack (a published catalogue, metered traffic).
interface Account { email: string; role: string; password: string }
interface Org { slug: string; organization_id: string; accounts: Account[] }
const credentials = () => JSON.parse(readFileSync(process.env.FORGE_E2E_CREDENTIALS!, "utf8")) as { organizations: Org[] };

export function seededOrg(slug: "org-a" | "org-b") {
  const org = credentials().organizations.find((item) => item.slug === slug)!;
  return {
    id: org.organization_id,
    admin: org.accounts.find((account) => account.role === "organization_admin")!,
    member: org.accounts.find((account) => account.role === "member")!,
  };
}

// The control plane keeps at most eight live sessions per account (and five failed sign-ins per window): one session per account is
// reused for the whole run, and `releaseTokens` gives every one back when a journey is done, so nothing accumulates.
const sessions = new Map<string, string>();

export async function tokenFor(request: APIRequestContext, account: Account): Promise<string> {
  const key = `${account.email}\n${account.password}`;
  const known = sessions.get(key);
  if (known) return known;
  const login = await request.post("/forge/v1/accounts/login", { data: { email: account.email, password: account.password } });
  expect(login.ok(), "login").toBe(true);
  const token = ((await login.json()) as { access_token: string }).access_token;
  sessions.set(key, token);
  return token;
}

/** Signs out every session `tokenFor` opened; a session the server already ended is not an error. */
export async function releaseTokens(request: APIRequestContext): Promise<void> {
  const open = [...sessions.values()];
  sessions.clear();
  for (const token of open) await request.post("/forge/v1/accounts/logout", { headers: { Authorization: `Bearer ${token}` } });
}

/** Publishes a catalogue for the organization when it has none, then returns the alias a member can chat with. */
export async function ensureCatalogue(request: APIRequestContext, orgId: string, adminToken: string, model = "fake-fast"): Promise<string> {
  const headers = { Authorization: `Bearer ${adminToken}` };
  const published = await request.get(`/forge/v1/orgs/${orgId}/models`, { headers });
  if (published.ok()) return ((await published.json()) as { models: Array<{ id: string }> }).models[0]!.id;
  const status = (await (await request.get(`/forge/v1/orgs/${orgId}/gateway/catalogue/status`, { headers })).json()) as { catalogue_revision: number };
  const refresh = await request.post(`/forge/v1/orgs/${orgId}/gateway/catalogue/refresh`, { headers });
  expect(refresh.ok(), "catalogue refresh").toBe(true);
  const discovered = (await refresh.json()) as { gateway_revision: number; model_ids: string[] };
  const publish = await request.post(`/forge/v1/orgs/${orgId}/models/publish`, {
    headers,
    data: { operation_id: randomUUID(), expected_catalogue_revision: status.catalogue_revision, expected_gateway_revision: discovered.gateway_revision, aliases: { fast: discovered.model_ids.includes(model) ? model : discovered.model_ids[0] }, default_alias: "fast" },
  });
  expect(publish.ok(), "catalogue publish").toBe(true);
  return "fast";
}

/** One real streamed chat through the fake gateway as the company's member: the platform meters it. */
export async function meteredChat(request: APIRequestContext, orgId: string, memberToken: string, alias: string): Promise<void> {
  const chat = await request.post(`/forge/v1/orgs/${orgId}/chat/completions`, {
    headers: { Authorization: `Bearer ${memberToken}` },
    data: { model: alias, messages: [{ role: "user", content: "Hello" }], stream: true },
  });
  expect(chat.status(), "chat status").toBe(200);
  expect(await chat.text()).toContain("[DONE]");
}
