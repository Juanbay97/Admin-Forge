import { existsSync, readFileSync, readdirSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { FONT_FAMILIES, FONT_IDS } from "../../src/brand/palette";

const TOKENS_CSS = readFileSync(new URL("../../src/brand/tokens.css", import.meta.url), "utf8");
const FONT_DIR = new URL("../../public/fonts/", import.meta.url);
const LICENCES: Record<string, string> = {
  inter: "Inter-OFL.txt",
  montserrat: "Montserrat-OFL.txt",
  "source-sans-3": "SourceSans3-OFL.txt",
  "ibm-plex-sans": "IBMPlexSans-OFL.txt",
  "nunito-sans": "NunitoSans-OFL.txt",
  roboto: "Roboto-OFL.txt",
};

test.describe("bundled fonts", () => {
  test("every vetted font is declared once, self-hosted, and its file and OFL licence ship", () => {
    for (const id of FONT_IDS) {
      const family = FONT_FAMILIES[id];
      const faces = [...TOKENS_CSS.matchAll(/@font-face\s*{[^}]*}/g)].map((match) => match[0]).filter((face) => face.includes(`font-family: "${family}"`));
      expect(faces, family).toHaveLength(1);
      const file = /url\("\/admin\/fonts\/([a-z0-9-]+-latin-wght-normal\.woff2)"\)/.exec(faces[0]!)?.[1];
      expect(file, `${family} file`).toBe(`${id}-latin-wght-normal.woff2`);
      expect(existsSync(new URL(file!, FONT_DIR)), `${family} woff2`).toBe(true);
      const licence = readFileSync(new URL(LICENCES[id]!, FONT_DIR), "utf8");
      expect(licence, `${family} licence`).toContain("SIL Open Font License, Version 1.1");
    }
  });

  test("nothing but the vetted fonts, their licences and the source record is bundled", () => {
    const expected = [
      ...FONT_IDS.map((id) => `${id}-latin-wght-normal.woff2`),
      ...Object.values(LICENCES),
      "SOURCES.md",
    ].sort();
    expect(readdirSync(FONT_DIR).sort()).toEqual(expected);
  });

  test("no remote font or stylesheet is referenced", () => {
    expect(TOKENS_CSS).not.toMatch(/https?:|@import\s+url|\/\/[a-z]/i);
  });
});
