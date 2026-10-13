import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createUsageApi, parseMemberRows } from "../../src/api/usage";

const fixture = (name: string): unknown => JSON.parse(readFileSync(new URL(`../fixtures/portal/${name}.json`, import.meta.url), "utf8"));
const ORG = "11111111-1111-4111-8111-111111111111";

function api(replies: Record<string, unknown | ApiError>) {
  const calls: string[] = [];
  const client: ApiClient = {
    async request(method, path) {
      calls.push(`${method} ${path}`);
      const reply = replies[path.split("?")[0]!];
      if (reply instanceof ApiError) throw reply;
      if (reply === undefined) throw new ApiError(404, "NOT_FOUND", "x");
      return reply as never;
    },
  };
  return { usage: createUsageApi(client), calls };
}

test.describe("own usage (the member's contract)", () => {
  test("parses the counters for the window", async () => {
    const { usage, calls } = api({ [`/forge/v1/orgs/${ORG}/usage/me`]: fixture("usage-me") });
    const mine = await usage.mine(ORG, { from: "2026-10-01", to: "2026-10-12" });
    expect(mine).toMatchObject({ requests: 12, prompt_tokens: 8000, cost_micros: 150000 });
    expect(calls).toEqual([`GET /forge/v1/orgs/${ORG}/usage/me?from=2026-10-01&to=2026-10-12`]);
  });
  test("a server without the route (404) is `null`, so the page can say it is not available yet", async () => {
    expect(await api({}).usage.mine(ORG, { from: "2026-10-01", to: "2026-10-12" })).toBeNull();
  });
  test("other failures and drifted shapes are errors", async () => {
    await expect(api({ [`/forge/v1/orgs/${ORG}/usage/me`]: new ApiError(503, "SERVICE_UNAVAILABLE", "x") }).usage.mine(ORG, { from: "2026-10-01", to: "2026-10-12" })).rejects.toMatchObject({ status: 503 });
    await expect(api({ [`/forge/v1/orgs/${ORG}/usage/me`]: { tokens: 5 } }).usage.mine(ORG, { from: "2026-10-01", to: "2026-10-12" })).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

test.describe("company per-person usage (the real route)", () => {
  test("parses members with their counters and the next cursor", async () => {
    const { usage, calls } = api({ [`/forge/v1/orgs/${ORG}/usage/members`]: fixture("usage-members") });
    const page = await usage.members(ORG, { from: "2026-10-01", to: "2026-10-12" });
    expect(page.members.map((member) => member.name)).toEqual(["Alex Admin", "Pat Member", "Sam Suspended"]);
    expect(page.members[0]).toMatchObject({ email: "alex@acme.test", state: "active", cost_micros: 900000 });
    expect(calls).toEqual([`GET /forge/v1/orgs/${ORG}/usage/members?from=2026-10-01&to=2026-10-12&page=100`]);
  });
  test("every page is followed through the member cursor", async () => {
    const pages = [
      { members: [{ ...(fixture("usage-members") as { members: Array<Record<string, unknown>> }).members[0]! }], next_after: "a1111111-1111-4111-8111-111111111111" },
      { members: [{ ...(fixture("usage-members") as { members: Array<Record<string, unknown>> }).members[1]! }], next_after: null },
    ];
    const seen: string[] = [];
    const client: ApiClient = { request: async (_m, path) => (seen.push(path), pages.shift() as never) };
    const all = await createUsageApi(client).allMembers(ORG, { from: "2026-10-01", to: "2026-10-12" });
    expect(all.map((member) => member.name)).toEqual(["Alex Admin", "Pat Member"]);
    expect(seen[1]).toContain("after=a1111111-1111-4111-8111-111111111111");
  });
  test("a malformed row fails the whole page with a precise error", () => {
    expect(() => parseMemberRows({ members: [{ member_id: "x" }], next_after: null })).toThrow(/INVALID|unexpected/i);
  });
});