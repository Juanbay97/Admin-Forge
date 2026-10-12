import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import {
  ASSET_URL_PREFIX,
  DEFAULT_BRANDING,
  draftFrom,
  draftToDocument,
  isDefaultLook,
  parseBranding,
  saveBlocker,
} from "../../src/brand/branding";
import { generatePalette } from "../../src/brand/palette";
import { defaultTheme, themeFromBranding } from "../../src/brand/theme";

const vectors = JSON.parse(readFileSync(new URL("../../../contract/branding-palette.vectors.json", import.meta.url), "utf8")) as {
  valid: Array<{ name: string; input: Parameters<typeof generatePalette>[0]; light: Record<string, string> }>;
};

const SHA = "a".repeat(64);
const served = () => ({
  revision: 3,
  name: "Acme Labs",
  loginCopy: "Sign in to the Acme workspace.",
  theme: { primary: "#1D4ED8", accent: "#B45309", tint: "#E5E7EB", heading: "source-sans-3", body: "roboto" },
  assets: { logoLight: ASSET_URL_PREFIX + SHA },
});

test.describe("branding model", () => {
  test("the asset URL form is the same-origin content-addressed path", () => {
    expect(ASSET_URL_PREFIX).toBe("/forge/v1/branding/assets/");
  });

  test("the default is the Prometheon theme at revision 0 (server defaults)", () => {
    expect(DEFAULT_BRANDING).toEqual({
      revision: 0,
      name: "Prometheon Forge",
      loginCopy: "Sign in to your Forge workspace.",
      theme: { primary: "#0B1D26", accent: "#E07A2D", tint: "#E8DCC1", heading: "montserrat", body: "inter" },
      assets: {},
    });
  });

  test("parseBranding accepts exactly the served shape", () => {
    expect(parseBranding(served())).toEqual(served());
    expect(parseBranding({ ...served(), assets: {} }).assets).toEqual({});
  });

  test("parseBranding refuses hostile or malformed payloads whole", () => {
    const bad: unknown[] = [
      null, [], "x", 3,
      { ...served(), extra: 1 },
      { ...served(), revision: -1 },
      { ...served(), revision: 1.5 },
      { ...served(), name: "" },
      { ...served(), name: "a".repeat(41) },
      { ...served(), name: "x\u202Ey" },
      { ...served(), loginCopy: "a\nb" },
      { ...served(), loginCopy: "z".repeat(281) },
      { ...served(), theme: { ...served().theme, primary: "red; } body{display:none" } },
      { ...served(), theme: { ...served().theme, heading: "comic" } },
      { ...served(), theme: { ...served().theme, extra: "#000000" } },
      { ...served(), theme: { primary: "#1D4ED8" } },
      { ...served(), assets: { logoLight: "https://evil.test/x.png" } },
      { ...served(), assets: { logoLight: ASSET_URL_PREFIX + "A".repeat(64) } },
      { ...served(), assets: { logoLight: ASSET_URL_PREFIX + SHA + "/../x" } },
      { ...served(), assets: { favicon: ASSET_URL_PREFIX + SHA } },
    ];
    for (const value of bad) expect(() => parseBranding(value), JSON.stringify(value)).toThrow();
  });

  test("a draft round-trips to the save document with hashes, not URLs", () => {
    const draft = draftFrom(parseBranding(served()));
    expect(draft).toMatchObject({ name: "Acme Labs", primary: "#1D4ED8", heading: "source-sans-3", assets: { logoLight: SHA } });
    expect(draftToDocument(draft)).toEqual({
      name: "Acme Labs",
      loginCopy: "Sign in to the Acme workspace.",
      theme: { primary: "#1D4ED8", accent: "#B45309", tint: "#E5E7EB", heading: "source-sans-3", body: "roboto" },
      assets: { logoLight: SHA },
    });
  });

  test("a draft document trims nothing and never invents asset keys", () => {
    const draft = { ...draftFrom(DEFAULT_BRANDING), name: "  spaced  " };
    expect(draftToDocument(draft).name).toBe("  spaced  ");
    expect(draftToDocument(draft).assets).toEqual({});
  });

  test("saving is blocked only when the server would accept but the apps could not build a readable theme", () => {
    const draft = draftFrom(DEFAULT_BRANDING);
    expect(saveBlocker(draft)).toBeNull();
    expect(saveBlocker({ ...draft, accent: "#FFEB3B" })).toMatch(/readable/);
    expect(saveBlocker({ ...draft, tint: "#000000" })).toMatch(/readable/);
    // The server is the authority for syntax and primary contrast: those go through so its error is shown.
    expect(saveBlocker({ ...draft, primary: "red" })).toBeNull();
    expect(saveBlocker({ ...draft, primary: "#FFFF00" })).toBeNull();
    expect(saveBlocker({ ...draft, accent: "#12" })).toBeNull();
  });

  test("default knobs keep the Prometheon look; anything else maps from the generated palette", () => {
    expect(isDefaultLook(DEFAULT_BRANDING.theme)).toBe(true);
    const renamed = themeFromBranding({ ...DEFAULT_BRANDING, revision: 5, name: "Renamed" });
    expect(renamed.colors).toEqual(defaultTheme.colors);
    expect(renamed.name).toBe("Renamed");
    expect(renamed.title).toBe("Renamed Admin");
    expect(renamed.fonts).toEqual(defaultTheme.fonts);

    const blue = vectors.valid.find((item) => item.name.startsWith("blue"))!;
    const theme = themeFromBranding({ ...parseBranding(served()), theme: blue.input });
    expect(theme.colors).toEqual({
      primary: blue.light["--ink-solid"],
      teal: blue.light["--brand-primary"],
      accent: blue.light["--brand-accent"],
      sand: blue.light["--surface-selected"],
      carbon: blue.light["--text-primary"],
    });
    expect(theme.fonts).toEqual({ title: "Source Sans 3", body: "Roboto" });
  });

  test("assets pick the right mark per background and favicon, falling back to the default art", () => {
    const base = parseBranding(served());
    const plain = themeFromBranding({ ...base, assets: {} });
    expect(plain.assets).toEqual(defaultTheme.assets);
    expect(plain.favicon).toBe(defaultTheme.favicon);
    const light = ASSET_URL_PREFIX + "1".repeat(64);
    const dark = ASSET_URL_PREFIX + "2".repeat(64);
    const iso = ASSET_URL_PREFIX + "3".repeat(64);
    const both = themeFromBranding({ ...base, assets: { logoLight: light, logoDark: dark, isotipo: iso } });
    expect(both.assets).toEqual({ markOnLight: light, markOnDark: dark });
    expect(both.favicon).toBe(iso);
    const onlyLight = themeFromBranding({ ...base, assets: { logoLight: light } });
    expect(onlyLight.assets).toEqual({ markOnLight: light, markOnDark: light });
    expect(onlyLight.favicon).toBe(light);
  });

  test("a theme the palette cannot express falls back to the default colours", () => {
    const theme = themeFromBranding({ ...parseBranding(served()), theme: { ...served().theme, accent: "#FFEB3B" } as never });
    expect(theme.colors).toEqual(defaultTheme.colors);
  });
});
