import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createPlatformApi, type PlatformApi } from "../../src/api/platform";
import { usd, microsFromUsd } from "../../src/platform/money";

const fixture = (name: string): unknown => JSON.parse(readFileSync(new URL(`../fixtures/platform/${name}.json`, import.meta.url), "utf8"));

interface Call { method: string; path: string; body?: unknown }
function api(replies: Record<string, unknown>): { api: PlatformApi; calls: Call[] } {
  const calls: Call[] = [];
  const client: ApiClient = {
    async request(method, path, body) {
      calls.push({ method, path, body });
      const reply = replies[`${method} ${path.split("?")[0]}`];
      if (reply === undefined) throw new ApiError(404, "NOT_FOUND", "x");
      return reply as never;
    },
  };
  return { api: createPlatformApi(client), calls };
}

const P = "/forge/v1/platform";
const ORG = "11111111-1111-4111-8111-111111111111";

test.describe("platform contract (fixtures are the real response shapes)", () => {
  test("me, enrollment and the verification step", async () => {
    const { api: platform, calls } = api({ [`GET ${P}/me`]: fixture("me"), [`POST ${P}/mfa/enroll`]: fixture("enrollment"), [`POST ${P}/login/mfa`]: { verified: true } });
    expect((await platform.me()).mfa).toEqual({ state: "active", verified: true, fresh: true });
    expect((await platform.enroll()).recovery_codes).toHaveLength(2);
    await platform.verify({ code: "123456" });
    await platform.verify({ recovery_code: "aaaa-bbbb-cccc" });
    expect(calls.slice(-2).map((call) => call.body)).toEqual([{ code: "123456" }, { recovery_code: "aaaa-bbbb-cccc" }]);
  });

  test("companies, create, suspend and audit parse and send the real bodies", async () => {
    const { api: platform, calls } = api({
      [`GET ${P}/companies`]: fixture("companies"),
      [`POST ${P}/companies`]: fixture("company-created"),
      [`POST ${P}/companies/${ORG}/suspend`]: { id: ORG, slug: "acme", display_name: "Acme Corp", active: false },
      [`GET ${P}/audit`]: fixture("audit"),
    });
    const list = await platform.companies({ after: "acme" });
    expect(list.companies.map((company) => company.slug)).toEqual(["acme", "globex"]);
    expect(calls[0]?.path).toBe(`${P}/companies?after=acme`);
    const created = await platform.createCompany({ slug: "initech", display_name: "Initech", department: "General", admin_email: "ada@initech.test", admin_name: "Ada" });
    expect(created.invitation.delivery_state).toBe("delivered");
    expect((await platform.suspend(ORG)).active).toBe(false);
    expect((await platform.audit({ before: 12 })).entries[0]?.action).toBe("company.suspended");
    expect(calls.at(-1)?.path).toBe(`${P}/audit?before=12`);
  });

  test("gateway keys, assignments, model access, prices and usage", async () => {
    const { api: platform, calls } = api({
      [`GET ${P}/gateway-keys`]: fixture("gateway-keys"),
      [`GET ${P}/companies/${ORG}/gateway-keys`]: fixture("company-keys"),
      [`PUT ${P}/companies/${ORG}/gateway-keys`]: fixture("company-keys"),
      [`GET ${P}/companies/${ORG}/model-access`]: fixture("model-access"),
      [`GET ${P}/prices`]: fixture("prices"),
      [`GET ${P}/usage/totals`]: fixture("usage-totals"),
      [`GET ${P}/usage/companies`]: fixture("usage-companies"),
      [`GET ${P}/usage/models`]: fixture("usage-models"),
    });
    expect((await platform.keys()).keys[0]?.hint).toBe("a1b2");
    expect((await platform.companyKeys(ORG)).keys[0]?.priority).toBe(1);
    await platform.assignKeys(ORG, [{ key_id: "55555555-5555-4555-8555-555555555555", priority: 1, active: true }]);
    expect(calls.at(-1)?.body).toEqual({ keys: [{ key_id: "55555555-5555-4555-8555-555555555555", priority: 1, active: true }] });
    expect((await platform.modelAccess(ORG)).models).toEqual(["gpt-4o", "gpt-4o-mini"]);
    expect((await platform.prices()).prices[0]?.input_micros).toBe(2_500_000);
    expect((await platform.usageTotals({ from: "2026-10-01", to: "2026-10-12" })).cost_micros).toBe(42_000);
    expect(calls.at(-1)?.path).toBe(`${P}/usage/totals?from=2026-10-01&to=2026-10-12`);
    expect((await platform.usageByCompany({ from: "2026-10-01", to: "2026-10-12" })).companies[0]?.slug).toBe("acme");
    expect((await platform.usageByModel({ from: "2026-10-01", to: "2026-10-12" })).models[0]?.upstream_id).toBe("gpt-4o");
  });

  test("drift fails at the boundary with a precise error instead of rendering undefined", async () => {
    const drifted = { companies: [{ id: ORG, slug: "acme", display_name: "Acme", is_active: true }], next_after: null };
    const { api: platform } = api({ [`GET ${P}/companies`]: drifted, [`GET ${P}/me`]: { account_id: "x", role: "platform_owner", mfa: "totp" } });
    await expect(platform.companies({})).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    await expect(platform.me()).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  test("a secret never appears in what the client keeps: create key sends the key once and returns metadata only", async () => {
    const { api: platform, calls } = api({ [`POST ${P}/gateway-keys`]: { ...(fixture("gateway-keys") as { keys: unknown[] }).keys[0] as object } });
    const created = await platform.createKey({ label: "Primary", origin: "https://gateway.example.test", key: "sk-super-secret-1234" });
    expect(JSON.stringify(created)).not.toContain("sk-super-secret");
    expect(calls[0]?.body).toEqual({ label: "Primary", origin: "https://gateway.example.test", key: "sk-super-secret-1234" });
  });
});

test.describe("money", () => {
  test("USD strings convert to micro-USD by decimal string math, never floats", () => {
    expect(microsFromUsd("3.00")).toBe(3_000_000);
    expect(microsFromUsd("15")).toBe(15_000_000);
    expect(microsFromUsd("0.000001")).toBe(1);
    expect(microsFromUsd("0.1")).toBe(100_000);
    expect(microsFromUsd("999.999999")).toBe(999_999_999);
    expect(microsFromUsd("1000")).toBe(1_000_000_000);
  });
  test("rejects negatives, more than six decimals, junk and values over the server cap", () => {
    for (const bad of ["-1", "1.0000001", "abc", "", "1e3", "1,5", " 3", "1000.000001", "."]) expect(microsFromUsd(bad), bad).toBeNull();
  });
  test("micros format back to an exact USD string", () => {
    expect(usd(3_000_000)).toBe("3.00");
    expect(usd(1)).toBe("0.000001");
    expect(usd(2_500_000)).toBe("2.50");
    expect(usd(999_999_999)).toBe("999.999999");
  });
});