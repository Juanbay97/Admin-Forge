import { expect, test } from "@playwright/test";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createMembersApi, type Member } from "../../src/api/members";
import { applyUpdate, describeFailure, roleLabel, visiblePending } from "../../src/members/model";

const PAT: Member = {
  id: "m-pat",
  email: "pat@example.com",
  display_name: "Pat Member",
  status: "active",
  roles: ["member"],
  departments: [{ id: "d1", name: "Legal" }],
};
const ALEX: Member = { ...PAT, id: "m-alex", email: "alex@example.com", display_name: "Alex Admin", roles: ["organization_admin"] };

function recorder(reply: unknown) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const client: ApiClient = {
    async request<T>(method: string, path: string, body?: unknown) {
      calls.push({ method, path, body });
      return reply as T;
    },
  };
  return { calls, api: createMembersApi(client) };
}

test.describe("members api", () => {
  test("lists the members of one organization", async () => {
    const { api, calls } = recorder({ members: [PAT, ALEX] });
    expect(await api.list("org/1")).toEqual([PAT, ALEX]);
    expect(calls).toEqual([{ method: "GET", path: "/forge/v1/orgs/org%2F1/members", body: undefined }]);
  });

  test("assigns a department with one PUT that carries only the department id and returns the updated member", async () => {
    const { api, calls } = recorder({ ...PAT, departments: [{ id: "d2", name: "Support" }] });
    const updated = await api.assignDepartment("o1", "m 1", "d2");
    expect(updated.departments).toEqual([{ id: "d2", name: "Support" }]);
    expect(calls).toEqual([{ method: "PUT", path: "/forge/v1/orgs/o1/members/m%201/department", body: { department_id: "d2" } }]);
  });

  test("suspends and reactivates by member id", async () => {
    const { api, calls } = recorder({ ...PAT, status: "suspended" });
    expect((await api.suspend("o1", "m 1")).status).toBe("suspended");
    await api.reactivate("o1", "m 1");
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "POST /forge/v1/orgs/o1/members/m%201/suspend",
      "POST /forge/v1/orgs/o1/members/m%201/reactivate",
    ]);
  });

  test("invites with the department and returns the delivery receipt", async () => {
    const receipt = { invitation_id: "i1", expires_at: "later", delivery_state: "pending", delivery_channel: "local_mailbox" };
    const { api, calls } = recorder(receipt);
    expect(await api.invite("o1", { email: "new@example.com", name: "New Hire", departmentId: "d9" })).toEqual(receipt);
    expect(calls[0]).toEqual({
      method: "POST",
      path: "/forge/v1/accounts/invitations",
      body: { organization_id: "o1", department_id: "d9", email: "new@example.com", name: "New Hire" },
    });
  });
});

test.describe("member model", () => {
  test("administrators are labelled before plain membership", () => {
    expect(roleLabel(["member", "organization_admin"])).toBe("Administrator");
    expect(roleLabel(["member"])).toBe("Member");
    expect(roleLabel([])).toBe("Member");
  });

  test("an update replaces only the matching member and keeps the order", () => {
    const updated = { ...PAT, status: "suspended" as const };
    expect(applyUpdate([ALEX, PAT], updated)).toEqual([ALEX, updated]);
    expect(applyUpdate([ALEX], updated)).toEqual([ALEX]);
  });

  test("a pending invitation disappears once that email is a member", () => {
    const pending = [
      { email: "Pat@Example.com", name: "Pat", departmentName: "Legal" },
      { email: "new@example.com", name: "New", departmentName: "Legal" },
    ];
    expect(visiblePending(pending, [PAT]).map((p) => p.email)).toEqual(["new@example.com"]);
    expect(visiblePending(pending, []).map((p) => p.email)).toEqual(["Pat@Example.com", "new@example.com"]);
  });

  test("failures become redacted, actionable messages", () => {
    const lastAdmin = new ApiError(409, "LAST_ADMIN", "internal detail");
    expect(describeFailure(lastAdmin, "suspend")).toBe(
      "This is the last administrator. Make another member an administrator before suspending this one.",
    );
    expect(describeFailure(new ApiError(404, "NOT_FOUND", "x"), "reactivate")).toBe(
      "This member is no longer available. Reload the list.",
    );
    expect(describeFailure(new ApiError(422, "INVALID_REQUEST", "x"), "invite")).toBe(
      "The invitation could not be sent. Check the name and email, then try again.",
    );
    expect(describeFailure(new ApiError(0, "NETWORK", "x"), "suspend")).toBe("The change could not be saved. Try again.");
    expect(describeFailure(new Error("boom"), "load")).toBe("The members could not be loaded. Try again.");
  });
});
