import { expect, test } from "@playwright/test";
import { AREAS, areaOfPath, navFor } from "../../src/shell/areas";

const admin = { account: { id: "a", email: "a@example.com", display_name: "A" }, platform: null, orgs: [{ id: "o", display_name: "O", status: "active" as const, roles: ["organization_admin"], departments: [] }] };

test.describe("area registry", () => {
  test("only the company area is open; platform and portal are registered stubs", () => {
    expect(Object.values(AREAS).filter((area) => area.enabled).map((area) => area.id)).toEqual(["company"]);
    expect(AREAS.platform.enabled).toBe(false);
    expect(AREAS.portal.enabled).toBe(false);
  });
  test("a path belongs to the area that owns its first segment", () => {
    expect(areaOfPath("/company/members")).toBe("company");
    expect(areaOfPath("/platform")).toBe("platform");
    expect(areaOfPath("/portal/chat")).toBe("portal");
    expect(areaOfPath("/")).toBeNull();
    expect(areaOfPath("/companyx")).toBeNull();
  });
  test("company navigation lists the five pages in order and hides entries the user may not use", () => {
    expect(navFor(AREAS.company, admin).map((item) => item.label)).toEqual(["Overview", "Members", "Gateway", "Catalog", "Branding"]);
    expect(navFor(AREAS.company, admin).map((item) => item.to)).toEqual(["/company", "/company/members", "/company/gateway", "/company/catalog", "/company/branding"]);
    expect(navFor({ ...AREAS.company, nav: [...AREAS.company.nav, { label: "Secret", to: "/company/secret", icon: "shield", requires: () => false }] }, admin)).toHaveLength(5);
  });
  test("a company admin may enter the company area and not the platform area", () => {
    expect(AREAS.company.requires(admin)).toBe(true);
    expect(AREAS.platform.requires(admin)).toBe(false);
  });
});