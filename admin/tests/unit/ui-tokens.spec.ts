import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const CSS = readFileSync(new URL("../../src/brand/tokens.css", import.meta.url), "utf8");

/** Declarations of the rule whose selector matches exactly, found by balancing braces. */
function declarations(selector: string): Map<string, string> {
  const start = CSS.indexOf(`${selector} {`);
  expect(start, `rule ${selector} exists in tokens.css`).toBeGreaterThanOrEqual(0);
  const open = CSS.indexOf("{", start);
  let depth = 0;
  let close = open;
  for (; close < CSS.length; close++) {
    if (CSS[close] === "{") depth++;
    if (CSS[close] === "}" && --depth === 0) break;
  }
  const body = CSS.slice(open + 1, close);
  return new Map([...body.matchAll(/(--[a-z0-9-]+|color-scheme)\s*:\s*([^;]+);/g)].map((match) => [match[1]!, match[2]!.trim()]));
}

const REQUIRED = [
  "--ui-bg", "--ui-surface", "--ui-surface-raised", "--ui-border", "--ui-fg", "--ui-fg-muted", "--ui-primary", "--ui-primary-fg",
  "--ui-accent", "--ui-ring", "--ui-success", "--ui-warning", "--ui-destructive",
  "--ui-chart-1", "--ui-chart-2", "--ui-chart-3", "--ui-chart-4", "--ui-chart-5",
];
// Fixed neutrals and status colours that are not part of a company palette; everything else must come from `--brand-*`.
const NEUTRAL = /^--ui-(?:surface|surface-raised|primary-fg|(?:success|warning|destructive)(?:-soft|-fg|-hover|-text)?)$/;

test.describe("semantic --ui-* tokens", () => {
  const lightTokens = () => declarations(":root");

  test("define every token the kit styles through", () => {
    const light = lightTokens();
    for (const name of REQUIRED) expect(light.has(name), name).toBe(true);
  });

  test("each token is derived from a --brand-* variable unless it is a documented neutral", () => {
    const own = [...lightTokens()].filter(([name]) => name.startsWith("--ui-"));
    expect(own.length).toBeGreaterThanOrEqual(REQUIRED.length);
    const unmapped = own.filter(([name, value]) => !NEUTRAL.test(name) && !value.includes("var(--brand-")).map(([name]) => name);
    expect(unmapped).toEqual([]);
  });

  test("dark mode overrides only --ui-* tokens, never the --brand-* variables the applier writes inline", () => {
    const dark = declarations(':root[data-mode="dark"]');
    const names = [...dark.keys()].filter((name) => name !== "color-scheme");
    expect(names.length).toBeGreaterThan(8);
    expect(names.filter((name) => !name.startsWith("--ui-"))).toEqual([]);
    for (const name of ["--ui-bg", "--ui-surface", "--ui-fg", "--ui-primary", "--ui-primary-fg"]) expect(dark.has(name), name).toBe(true);
  });

  test("type scale and radii follow the design", () => {
    const theme = declarations("@theme inline");
    expect(theme.get("--text-page")).toBe("1.5rem");
    expect(theme.get("--text-page--line-height")).toBe("2rem");
    expect(theme.get("--text-body")).toBe("0.875rem");
    expect(theme.get("--text-body--line-height")).toBe("1.25rem");
    expect(theme.get("--text-caption")).toBe("0.75rem");
    expect(theme.get("--radius-control")).toBe("0.5rem");
    expect(theme.get("--radius-card")).toBe("0.75rem");
  });
});