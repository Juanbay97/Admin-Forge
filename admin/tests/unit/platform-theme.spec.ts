import { expect, test } from "@playwright/test";
import { contrastOfHex } from "../../src/brand/palette";
import { defaultTheme } from "../../src/brand/theme";
import { applyPlatformTheme, platformTheme } from "../../src/brand/platformTheme";

test.describe("platform theme", () => {
  test("is the fixed Prometheon look and carries no company asset", () => {
    expect(platformTheme.colors).toEqual(defaultTheme.colors);
    expect(platformTheme.fonts).toEqual({ title: "Montserrat", body: "Inter" });
    const urls = [...Object.values(platformTheme.assets), platformTheme.favicon];
    expect(urls).toHaveLength(3);
    expect(urls.filter((url) => !url.startsWith("/admin/brand/") || url.includes("/forge/v1/branding/assets/"))).toEqual([]);  });

  test("its text and action colours are readable", () => {
    const { primary, teal, carbon, sand } = platformTheme.colors;
    expect(contrastOfHex(carbon, "#FFFFFF")).toBeGreaterThanOrEqual(7);
    expect(contrastOfHex(carbon, sand)).toBeGreaterThanOrEqual(7);
    expect(contrastOfHex(teal, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    expect(contrastOfHex("#FFFFFF", primary)).toBeGreaterThanOrEqual(7);
  });

  test("applyPlatformTheme overwrites a company theme variable by variable", () => {
    const vars = new Map<string, string>([["--brand-teal", "#0B5FFF"]]);
    const root = { style: { setProperty: (name: string, value: string) => void vars.set(name, value) } };
    expect(applyPlatformTheme(root)).toBe(true);
    expect(vars.get("--brand-teal")).toBe("#0F6B6D");
    expect(vars.get("--brand-font-title")).toBe('"Montserrat", system-ui, sans-serif');
  });
});