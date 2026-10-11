import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { applyBrandTheme, createTheme, defaultTheme } from "../../src/brand/theme";

const TOKENS_CSS = readFileSync(new URL("../../src/brand/tokens.css", import.meta.url), "utf8");

function fakeRoot() {
  const vars = new Map<string, string>();
  return { vars, root: { style: { setProperty: (name: string, value: string) => void vars.set(name, value) } } };
}

test.describe("brand theme", () => {
  test("carries the Prometheon palette and typefaces", () => {
    expect(defaultTheme.name).toBe("Prometheon Forge");
    expect(defaultTheme.colors).toEqual({
      primary: "#0B1D26",
      teal: "#0F6B6D",
      accent: "#E07A2D",
      sand: "#E8DCC1",
      carbon: "#1A1A1A",
    });
    expect(defaultTheme.fonts).toEqual({ title: "Montserrat", body: "Inter" });
  });

  test("applyBrandTheme writes every token as a CSS variable", () => {
    const { vars, root } = fakeRoot();
    applyBrandTheme(defaultTheme, root);
    expect(Object.fromEntries(vars)).toEqual({
      "--brand-primary": "#0B1D26",
      "--brand-teal": "#0F6B6D",
      "--brand-accent": "#E07A2D",
      "--brand-sand": "#E8DCC1",
      "--brand-carbon": "#1A1A1A",
      "--brand-font-title": '"Montserrat", system-ui, sans-serif',
      "--brand-font-body": '"Inter", system-ui, sans-serif',
    });
  });

  test("a company theme is a swapped object, not a component edit", () => {
    const acme = createTheme({ name: "Acme", colors: { teal: "#123456" } });
    expect(acme.name).toBe("Acme");
    expect(acme.colors.teal).toBe("#123456");
    expect(acme.colors.primary).toBe(defaultTheme.colors.primary);
    const { vars, root } = fakeRoot();
    applyBrandTheme(acme, root);
    expect(vars.get("--brand-teal")).toBe("#123456");
  });

  test("the stylesheet only references the theme variables (single source)", () => {
    expect(TOKENS_CSS).not.toMatch(/#[0-9a-fA-F]{6}\b/);
    expect(TOKENS_CSS).toContain("var(--brand-primary)");
  });

  test("the stylesheet self-hosts both typefaces", () => {
    expect(TOKENS_CSS).toMatch(/font-family:\s*"Montserrat"[^}]*\/admin\/fonts\/montserrat-latin-wght-normal\.woff2/s);
    expect(TOKENS_CSS).toMatch(/font-family:\s*"Inter"[^}]*\/admin\/fonts\/inter-latin-wght-normal\.woff2/s);
    expect(TOKENS_CSS).not.toMatch(/https?:/);
  });
});
