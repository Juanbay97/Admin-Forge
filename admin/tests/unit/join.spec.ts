import { expect, test } from "@playwright/test";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createInvitationsApi } from "../../src/api/invitations";
import { joinStateFor } from "../../src/public/joinState";
import { passwordHints } from "../../src/public/passwordHints";

const ID = "3f2c1a9e-8b7d-4c6a-9e5f-0a1b2c3d4e5f";
const CAP = "A".repeat(43);

test.describe("invitation api", () => {
  const client = (reply: unknown): { client: ApiClient; calls: Array<{ method: string; path: string; body: unknown }> } => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    return { calls, client: { request: async (method, path, body) => (calls.push({ method, path, body }), reply as never) } };
  };
  test("accept posts exactly the invitation, the capability and the password, and parses the enrollment", async () => {
    const { client: c, calls } = client({ account_id: ID, organization_id: ID, membership_id: ID, department_id: ID });
    const result = await createInvitationsApi(c).accept({ invitationId: ID, capability: CAP, password: "a-long-enough-password" });
    expect(calls).toEqual([{ method: "POST", path: "/forge/v1/accounts/invitations/accept", body: { invitation_id: ID, capability: CAP, password: "a-long-enough-password" } }]);
    expect(result.organization_id).toBe(ID);
  });
  test("a reply of another shape is an INVALID_RESPONSE, not a half-built object", async () => {
    await expect(createInvitationsApi(client({ account_id: ID }).client).accept({ invitationId: ID, capability: CAP, password: "x".repeat(15) })).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

test.describe("join state", () => {
  test("the server folds expired, used, wrong and unknown invitations into one 404", () => {
    expect(joinStateFor(new ApiError(404, "NOT_FOUND", "x"))).toBe("invalid");
  });
  test("an existing account that must sign in first, a refused password, throttling and outages are distinct", () => {
    expect(joinStateFor(new ApiError(409, "EXISTING_ACCOUNT_AUTH_REQUIRED", "x"))).toBe("existing_account");
    expect(joinStateFor(new ApiError(422, "INVALID_REQUEST", "x"))).toBe("password");
    expect(joinStateFor(new ApiError(429, "AUTHENTICATION_TEMPORARILY_BLOCKED", "x"))).toBe("throttled");
    expect(joinStateFor(new ApiError(503, "SERVICE_UNAVAILABLE", "x"))).toBe("unavailable");
    expect(joinStateFor(new ApiError(0, "NETWORK", "x"))).toBe("offline");
    expect(joinStateFor(new Error("boom"))).toBe("unavailable");
  });
});

test.describe("password hints", () => {
  test("length is the one hard rule, counted in characters", () => {
    expect(passwordHints("short")).toEqual({ longEnough: false, remaining: 10 });
    expect(passwordHints("a".repeat(15))).toEqual({ longEnough: true, remaining: 0 });
    expect(passwordHints("é".repeat(15)).longEnough).toBe(true);
  });
});