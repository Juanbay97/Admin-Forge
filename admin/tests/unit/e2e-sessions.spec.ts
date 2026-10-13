import { expect, test } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import { releaseTokens, tokenFor } from "../../e2e/support/api";

// The control plane keeps at most eight live sessions per account, and a long run shares one stack: the API helpers must reuse a
// session per account and give every one of them back, so repeated journeys never exhaust it.
function fake() {
  const calls: Array<{ path: string; email?: string; auth?: string }> = [];
  let issued = 0;
  const request = {
    async post(path: string, options: { data?: { email: string }; headers?: { Authorization: string } }) {
      calls.push({ path, email: options.data?.email, auth: options.headers?.Authorization });
      const body = path.endsWith("login") ? { access_token: `token-${++issued}` } : {};
      return { ok: () => true, status: () => (path.endsWith("logout") ? 204 : 200), json: async () => body };
    },
  } as unknown as APIRequestContext;
  return { request, calls };
}
const account = (email: string) => ({ email, role: "member", password: "a-long-enough-password" });

test.describe("e2e API sessions", () => {
  test("one login per account however often a journey asks, and every session is given back once", async () => {
    const { request, calls } = fake();
    const first = await tokenFor(request, account("a@x.test"));
    expect(await tokenFor(request, account("a@x.test"))).toBe(first);
    const other = await tokenFor(request, account("b@x.test"));
    expect(other).not.toBe(first);
    expect(calls.filter((call) => call.path.endsWith("login"))).toHaveLength(2);
    await releaseTokens(request);
    expect(calls.filter((call) => call.path.endsWith("logout")).map((call) => call.auth).sort()).toEqual([`Bearer ${first}`, `Bearer ${other}`]);
    await releaseTokens(request);
    expect(calls.filter((call) => call.path.endsWith("logout"))).toHaveLength(2);
    expect(await tokenFor(request, account("a@x.test"))).not.toBe(first);
  });
});