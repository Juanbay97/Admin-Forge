import { expect, test } from "@playwright/test";
import { adminOrganizations, resolveEntry } from "../../src/auth/access";
import type { Me } from "../../src/api/account";

const ORG_A = { id: "11111111-1111-4111-8111-111111111111", display_name: "Org A", status: "active" as const, departments: [] };
const ORG_B = { id: "22222222-2222-4222-8222-222222222222", display_name: "Org B", status: "active" as const, departments: [] };

function me(...organizations: Me["organizations"]): Me {
  return { account: { id: "acc", email: "a@example.com", display_name: "Alex" }, organizations };
}

test.describe("entry resolution", () => {
  test("a single admin organisation is selected automatically", () => {
    const entry = resolveEntry(me({ ...ORG_A, roles: ["organization_admin"] }));
    expect(entry).toEqual({ kind: "ready", organization: { ...ORG_A, roles: ["organization_admin"] } });
  });

  test("several admin organisations require an explicit choice", () => {
    const entry = resolveEntry(
      me({ ...ORG_A, roles: ["organization_admin"] }, { ...ORG_B, roles: ["organization_admin", "member"] }),
    );
    expect(entry.kind).toBe("choose");
    if (entry.kind === "choose") expect(entry.organizations.map((o) => o.id)).toEqual([ORG_A.id, ORG_B.id]);
  });

  test("organisations where the user is only a member are never offered", () => {
    const entries = me({ ...ORG_A, roles: ["member"] }, { ...ORG_B, roles: ["organization_admin"] });
    expect(adminOrganizations(entries).map((o) => o.id)).toEqual([ORG_B.id]);
    expect(resolveEntry(entries).kind).toBe("ready");
  });

  test("a plain member is denied", () => {
    expect(resolveEntry(me({ ...ORG_A, roles: ["member"] }))).toEqual({ kind: "denied" });
  });

  test("an account with no organisation is denied", () => {
    expect(resolveEntry(me())).toEqual({ kind: "denied" });
  });
});
