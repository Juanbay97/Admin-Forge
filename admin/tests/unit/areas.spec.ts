import { expect, test } from "@playwright/test";
import { t } from "../../src/i18n/config";
import { AREAS, areaOfPath, navFor } from "../../src/shell/areas";

const admin = { account: { id: "a", email: "a@example.com", display_name: "A" }, platform: null, orgs: [{ id: "o", display_name: "O", status: "active" as const, roles: ["organization_admin"], departments: [] }] };

test.describe("area registry", () => {
  test("all three areas are open", () => {
    expect(Object.values(AREAS).filter((area) => area.enabled).map((area) => area.id)).toEqual(["platform", "company", "portal"]);
  });
  test("platform navigation lists the five console pages", () => {
    const owner = { ...admin, orgs: [], platform: { role: "platform_owner" as const, mfa: { state: "active" as const, verified: true, fresh: true } } };
    expect(navFor(AREAS.platform, owner).map((item) => item.to)).toEqual(["/platform", "/platform/companies", "/platform/keys", "/platform/prices", "/platform/audit"]);
    expect(navFor(AREAS.platform, owner).map((item) => t(item.labelKey))).toEqual(["Overview", "Companies", "Gateway keys", "Prices", "Audit log"]);
  });
  test("only a platform owner may enter the platform area, whatever else they administer", () => {
    const owner = { ...admin, platform: { role: "platform_owner" as const, mfa: { state: "none" as const, verified: false, fresh: false } } };
    expect(AREAS.platform.requires(owner)).toBe(true);
    expect(AREAS.platform.requires({ ...owner, platform: { ...owner.platform, role: "platform_viewer" as never } })).toBe(false);
  });
  test("a path belongs to the area that owns its first segment", () => {
    expect(areaOfPath("/company/members")).toBe("company");
    expect(areaOfPath("/platform")).toBe("platform");
    expect(areaOfPath("/portal/chat")).toBe("portal");
    expect(areaOfPath("/")).toBeNull();
    expect(areaOfPath("/companyx")).toBeNull();
  });
  test("company navigation lists the six pages in order and hides entries the user may not use", () => {
    expect(navFor(AREAS.company, admin).map((item) => t(item.labelKey))).toEqual(["Overview", "Members", "Gateway", "Catalog", "Branding", "Download Prometheon Forge"]);
    expect(navFor(AREAS.company, admin).map((item) => item.to)).toEqual(["/company", "/company/members", "/company/gateway", "/company/catalog", "/company/branding", "/company/download"]);
    expect(navFor({ ...AREAS.company, nav: [...AREAS.company.nav, { labelKey: "nav.company.members", to: "/company/secret", icon: "shield", requires: () => false }] }, admin)).toHaveLength(6);
  });
  test("a company admin may enter the company area and not the platform area", () => {
    expect(AREAS.company.requires(admin)).toBe(true);
    expect(AREAS.platform.requires(admin)).toBe(false);
  });
});