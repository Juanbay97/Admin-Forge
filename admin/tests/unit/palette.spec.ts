import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { COLOR_TOKENS, FONT_IDS, generatePalette, type PaletteInput } from "../../src/brand/palette";

const HERE = dirname(fileURLToPath(import.meta.url));
const CONTRACT = resolve(HERE, "../../../contract/branding-palette.vectors.json");
const CLIENT_COPY = ["clients", "openyak", "frontend", "tests", "fixtures", "branding-palette.vectors.json"];

interface Vectors {
  algorithm: string;
  valid: Array<{
    name: string;
    input: PaletteInput;
    light: Record<string, string>;
    dark: Record<string, string>;
    fonts: Record<string, string>;
  }>;
  infeasible: Array<{ name: string; input: PaletteInput }>;
}

const normalise = (text: string) => text.replace(/\r\n/g, "\n");
const vectors = JSON.parse(normalise(readFileSync(CONTRACT, "utf8"))) as Vectors;

/** The client is a separate checkout: walk up from this worktree until its fixture is found. */
function findClientCopy(): string | undefined {
  for (let dir = HERE, previous = ""; dir !== previous; previous = dir, dir = dirname(dir)) {
    const candidate = join(dir, ...CLIENT_COPY);
    if (existsSync(candidate)) return candidate;
  }
  return undefined;
}

test.describe("palette generator", () => {
  test("reproduces every golden vector exactly", () => {
    expect(vectors.valid.length).toBeGreaterThanOrEqual(6);
    for (const item of vectors.valid) {
      const palette = generatePalette(item.input);
      expect(palette, item.name).not.toBeNull();
      expect(palette!.light, `${item.name} light`).toEqual(item.light);
      expect(palette!.dark, `${item.name} dark`).toEqual(item.dark);
      expect(palette!.fonts, `${item.name} fonts`).toEqual(item.fonts);
    }
  });

  test("returns null for every infeasible vector", () => {
    expect(vectors.infeasible.length).toBeGreaterThanOrEqual(5);
    for (const item of vectors.infeasible) expect(generatePalette(item.input), item.name).toBeNull();
  });

  test("emits the full token set for both modes and both fonts", () => {
    expect(COLOR_TOKENS).toHaveLength(26);
    const palette = generatePalette(vectors.valid[0]!.input)!;
    expect(Object.keys(palette.light).sort()).toEqual([...COLOR_TOKENS].sort());
    expect(Object.keys(palette.dark).sort()).toEqual([...COLOR_TOKENS].sort());
    expect(Object.keys(palette.fonts).sort()).toEqual(["--font-body", "--font-heading"]);
  });

  test("only ever emits plain colour literals and font stacks built from the vetted list", () => {
    const colour = /^(#[0-9A-F]{6}|rgba\(\d{1,3}, \d{1,3}, \d{1,3}, 0\.\d+\))$/;
    for (const item of vectors.valid) {
      const palette = generatePalette(item.input)!;
      for (const value of [...Object.values(palette.light), ...Object.values(palette.dark)]) expect(value).toMatch(colour);
      for (const value of Object.values(palette.fonts)) expect(value).toMatch(/^"[A-Za-z0-9 ]+", "Segoe UI", system-ui, -apple-system, sans-serif$/);
    }
  });

  test("refuses hostile and malformed knobs instead of echoing them", () => {
    const base = vectors.valid[0]!.input;
    const hostile = ["red", "#12", "#0F6B6D;}", "#0F6B6Dff", "javascript:1", "", "0F6B6D", "#0f6b6d "];
    for (const value of hostile) {
      for (const key of ["primary", "accent", "tint"] as const) {
        expect(generatePalette({ ...base, [key]: value }), `${key}=${value}`).toBeNull();
      }
    }
    for (const font of ["Comic", "inter, serif", "url(//x)", "", "Inter"]) {
      expect(generatePalette({ ...base, heading: font as never }), font).toBeNull();
      expect(generatePalette({ ...base, body: font as never }), font).toBeNull();
    }
    expect(generatePalette(null as never)).toBeNull();
    expect(generatePalette({ ...base, primary: 7 as never })).toBeNull();
  });

  test("accepts lower-case hex and normalises it", () => {
    const base = vectors.valid[0]!.input;
    const shouting = generatePalette(base)!;
    const lower = generatePalette({ ...base, primary: base.primary.toLowerCase(), tint: base.tint.toLowerCase() })!;
    expect(lower).toEqual(shouting);
  });

  test("the vetted font ids are the contract list", () => {
    expect([...FONT_IDS]).toEqual(["inter", "montserrat", "source-sans-3", "ibm-plex-sans", "nunito-sans", "roboto"]);
  });
});

test.describe("vector drift", () => {
  test("the contract states the algorithm the generators implement", () => {
    expect(vectors.algorithm).toContain("floor((2*(a*(100-pct)+b*pct)+100)/200)");
  });

  test("the client keeps the same algorithm, valid and infeasible vectors (EOL-normalised)", () => {
    const copy = findClientCopy();
    test.skip(!copy, "the client checkout is not next to this worktree");
    const client = JSON.parse(normalise(readFileSync(copy!, "utf8"))) as Vectors;
    expect(client.algorithm).toBe(vectors.algorithm);
    expect(client.valid).toEqual(vectors.valid);
    expect(client.infeasible).toEqual(vectors.infeasible);
  });
});
