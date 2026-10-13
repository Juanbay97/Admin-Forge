import { expect, test } from "@playwright/test";
import { filterCompanies, isCompanyCode, parseStatus, setupChecklist, slugFromName } from "../../src/platform/companies";

const companies = [
  { id: "1", slug: "acme", display_name: "Acme Corp", active: true },
  { id: "2", slug: "globex", display_name: "Globex International", active: false },
  { id: "3", slug: "initech", display_name: "Initech", active: true },
];

test.describe("company list rules", () => {
  test("status is all, active or suspended; anything else is all", () => {
    expect(parseStatus("active")).toBe("active");
    expect(parseStatus("suspended")).toBe("suspended");
    for (const bad of [null, "", "ACTIVE", "x", "all"]) expect(parseStatus(bad), String(bad)).toBe("all");
  });
  test("search matches name or code, ignoring case and surrounding space", () => {
    expect(filterCompanies(companies, { q: " GLOBEX ", status: "all" }).map((c) => c.id)).toEqual(["2"]);
    expect(filterCompanies(companies, { q: "corp", status: "all" }).map((c) => c.id)).toEqual(["1"]);
    expect(filterCompanies(companies, { q: "", status: "all" })).toHaveLength(3);
  });
  test("status filters combine with search", () => {
    expect(filterCompanies(companies, { q: "", status: "suspended" }).map((c) => c.id)).toEqual(["2"]);
    expect(filterCompanies(companies, { q: "c", status: "active" }).map((c) => c.id)).toEqual(["1", "3"]);
  });
});

test.describe("company code", () => {
  test("3 to 32 lowercase letters, digits and inner hyphens, starting with a letter or digit", () => {
    for (const ok of ["acme", "a-1", "abc", "x".repeat(32), "0day-co"]) expect(isCompanyCode(ok), ok).toBe(true);
    for (const bad of ["ab", "x".repeat(33), "Acme", "-acme", "ac me", "acme_co", "acmé", ""]) expect(isCompanyCode(bad), bad).toBe(false);
  });
  test("a code is suggested from the name", () => {
    expect(slugFromName("Acme Corp")).toBe("acme-corp");
    expect(slugFromName("  Ünïcode & Sons!  ")).toBe("unicode-sons");
    expect(slugFromName("A")).toBe("a");
    expect(slugFromName("x".repeat(60))).toHaveLength(32);
    expect(slugFromName("---")).toBe("");
  });
});

test.describe("setup checklist", () => {
  test("a company is set up when it has a gateway key and models; branding is optional (the default is Prometheon)", () => {
    expect(setupChecklist({ brandingRevision: 0, keyCount: 0, modelCount: 0 })).toEqual({ branding: false, keys: false, models: false, complete: false });
    expect(setupChecklist({ brandingRevision: 2, keyCount: 1, modelCount: 3 })).toEqual({ branding: true, keys: true, models: true, complete: true });
    expect(setupChecklist({ brandingRevision: 0, keyCount: 1, modelCount: 1 })).toMatchObject({ branding: false, complete: true });
    expect(setupChecklist({ brandingRevision: 5, keyCount: 1, modelCount: 0 }).complete).toBe(false);
  });
});