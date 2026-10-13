import { expect, test } from "@playwright/test";
import type { AccountApi, Me } from "../../src/api/account";
import { ApiError } from "../../src/api/client";
import type { PlatformApi } from "../../src/api/platform";
import { ERROR_MESSAGES, errorMessage, needsMfa } from "../../src/shell/errors";
import { homeFor, loadIdentity, type Identity } from "../../src/shell/identity";

const org = (id: string, roles: string[]) => ({ id, display_name: id, status: "active" as const, roles, departments: [] });
const me = (...orgs: ReturnType<typeof org>[]): Me => ({ account: { id: "a1", email: "a@example.com", display_name: "Ada" }, organizations: orgs });
const account = (value: Me): AccountApi => ({ login: async () => "", logout: async () => undefined, me: async () => value, departments: async () => [] });
const platform = (reply: () => Promise<{ role: "platform_owner" | "platform_viewer"; mfa: "none" | "totp" }>): PlatformApi & { calls: number } => {
  const api = { calls: 0, me: async () => (api.calls++, reply()) };
  return api;
};

test.describe("homeFor", () => {
  const identity = (overrides: Partial<Identity>): Identity => ({ account: me().account, platform: null, orgs: [], ...overrides });
  test("a platform role wins, even for someone who also administers a company", () => {
    expect(homeFor(identity({ platform: { role: "platform_owner", mfaLevel: "totp" } }))).toBe("platform");
    expect(homeFor(identity({ platform: { role: "platform_viewer", mfaLevel: "none" }, orgs: [org("a", ["organization_admin"])] }))).toBe("platform");
  });
  test("an organization administrator lands on the company area", () => {
    expect(homeFor(identity({ orgs: [org("a", ["member"]), org("b", ["organization_admin", "member"])] }))).toBe("company");
  });
  test("everyone else, including an account with no organization, lands on the portal", () => {
    expect(homeFor(identity({ orgs: [org("a", ["member"])] }))).toBe("portal");
    expect(homeFor(identity({}))).toBe("portal");
  });
});

test.describe("loadIdentity", () => {
  test("combines the account with the platform role", async () => {
    const api = platform(async () => ({ role: "platform_owner", mfa: "totp" }));
    const identity = await loadIdentity({ account: account(me(org("a", ["organization_admin"]))), platform: api });
    expect(identity.platform).toEqual({ role: "platform_owner", mfaLevel: "totp" });
    expect(identity.orgs.map((item) => item.id)).toEqual(["a"]);
    expect(identity.account.display_name).toBe("Ada");
  });
  test("403 and 404 from platform/me mean not a platform account, never an error", async () => {
    for (const status of [403, 404]) {
      const api = platform(async () => { throw new ApiError(status, "FORBIDDEN", "no"); });
      expect((await loadIdentity({ account: account(me()), platform: api })).platform).toBeNull();
      expect(api.calls).toBe(1);
    }
  });
  test("any other failure is an error", async () => {
    for (const status of [0, 401, 500]) {
      const api = platform(async () => { throw new ApiError(status, "X", "boom"); });
      await expect(loadIdentity({ account: account(me()), platform: api })).rejects.toBeInstanceOf(ApiError);
    }
  });
  test("without a platform area the probe is never made", async () => {
    const api = platform(async () => ({ role: "platform_owner", mfa: "none" }));
    const identity = await loadIdentity({ account: account(me()), platform: api }, { probePlatform: false });
    expect(identity.platform).toBeNull();
    expect(api.calls).toBe(0);
  });
});

test.describe("error messages", () => {
  test("map a code to its copy and fall back by status", () => {
    expect(errorMessage(new ApiError(409, "REVISION_CONFLICT", "x"))).toBe(ERROR_MESSAGES.REVISION_CONFLICT);
    expect(errorMessage(new ApiError(0, "NETWORK", "x"))).toBe("The server could not be reached.");
    expect(errorMessage(new ApiError(500, "UNKNOWN", "x"))).toBe("Something went wrong. Try again.");
    expect(errorMessage(new Error("plain"))).toBe("Something went wrong. Try again.");
  });
  test("MFA_REQUIRED is recognised so the shell can route to the MFA step", () => {
    expect(needsMfa(new ApiError(401, "MFA_REQUIRED", "x"))).toBe(true);
    expect(needsMfa(new ApiError(401, "UNAUTHENTICATED", "x"))).toBe(false);
    expect(needsMfa(null)).toBe(false);
  });
});