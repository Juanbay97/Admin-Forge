import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { ApiError } from "../../src/api/client";
import {
  ASSET_URL_PREFIX,
  DEFAULT_BRANDING,
  describeBrandingFailure,
  draftFrom,
  draftToDocument,
  isDefaultLook,
  paletteIssues,
  parseBranding,
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

test.describe("branding failures", () => {
  test("server refusals keep their message, conflicts prompt a reload, everything else is generic", () => {
    const refusal = new ApiError(422, "INVALID_REQUEST", "The product name must be 1 to 40 plain characters.");
    expect(describeBrandingFailure(refusal)).toBe("The product name must be 1 to 40 plain characters.");
    expect(describeBrandingFailure(new ApiError(413, "PAYLOAD_TOO_LARGE", "The image is larger than the allowed size."))).toBe(
      "The image is larger than the allowed size.",
    );
    expect(describeBrandingFailure(new ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Only PNG and WebP images are accepted."))).toBe(
      "Only PNG and WebP images are accepted.",
    );
    expect(describeBrandingFailure(new ApiError(409, "REVISION_CONFLICT", "The branding revision changed."))).toBe(
      "The branding was changed by another administrator. Reload to see the latest version; nothing was overwritten.",
    );
    expect(describeBrandingFailure(new ApiError(429, "RATE_LIMITED", "Too many requests."))).toBe("Too many requests. Wait a moment and try again.");
    expect(describeBrandingFailure(new ApiError(404, "NOT_FOUND", "x"))).toBe("Branding is not available for this organization.");
    expect(describeBrandingFailure(new ApiError(0, "NETWORK", "The server could not be reached."))).toBe("The server could not be reached.");
    for (const error of [new ApiError(503, "SERVICE_UNAVAILABLE", "boom"), new ApiError(200, "INVALID_RESPONSE", "x"), new Error("secret"), "x"]) {
      expect(describeBrandingFailure(error)).toBe("Something went wrong. Try again.");
    }
  });

  test("a message the server did not author is never echoed", () => {
    // 422 with an unexpected code (a proxy page, say) is not shown verbatim.
    expect(describeBrandingFailure(new ApiError(422, "UNKNOWN", "Request failed (422)."))).toBe("Something went wrong. Try again.");
  });
});
test.describe("live palette readability", () => {
  const draft = (change: Record<string, string> = {}) => ({ ...draftFrom(parseBranding(served())), ...change });

  test("a readable draft has no issue, and the rule is the shared generator's", () => {
    expect(paletteIssues(draft())).toEqual({});
    for (const vector of vectors.valid) {
      const { primary, accent, tint, heading, body } = vector.input;
      expect(paletteIssues({ ...draft(), primary, accent, tint, heading, body })).toEqual({});
    }
  });

  test("a malformed color names the field and shows an example", () => {
    const issues = paletteIssues(draft({ primary: "blue", tint: "#12" }));
    expect(issues.primary).toContain("hex color");
    expect(issues.tint).toContain("hex color");
    expect(issues.accent).toBeUndefined();
  });

  test("a primary or accent below 3:1 on white is flagged on its own field", () => {
    expect(paletteIssues(draft({ primary: "#FFEB3B" })).primary).toContain("3:1");
    expect(paletteIssues(draft({ accent: "#FFEB3B" })).accent).toContain("3:1");
  });

  test("a tint that cannot carry dark text is flagged on the tint", () => {
    expect(paletteIssues(draft({ tint: "#202020" })).tint).toContain("lighter");
  });

  test("every refusal of the generator surfaces some issue, so Save is never the first warning", () => {
    const hexes = ["#000000", "#FFFFFF", "#FFEB3B", "#1D4ED8", "#B45309", "#202020", "#E5E7EB", "#7C3AED", "#0B1D26"];
    for (const primary of hexes) for (const accent of hexes) for (const tint of hexes) {
      const value = draft({ primary, accent, tint });
      const refused = generatePalette({ primary, accent, tint, heading: value.heading, body: value.body }) === null;
      expect(Object.keys(paletteIssues(value)).length > 0, `${primary} ${accent} ${tint}`).toBe(refused);
    }
  });
});