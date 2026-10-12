// Deterministic palette generator: three colours and two font ids become the 26 colour tokens of
// both modes plus the two font stacks. The expansion is integer maths (floats only appear in the WCAG
// contrast check), so the admin, the client and the Python validators reproduce the golden vectors in
// `contract/branding-palette.vectors.json` byte for byte. Output values are only `#RRGGBB` and
// `rgba(n, n, n, 0.nn)` literals built from parsed numbers, plus font stacks from a fixed table:
// nothing the caller typed is ever copied into a CSS value.
//
// `generatePalette` returns null when the knobs cannot yield a readable theme.

export const FONT_IDS = ["inter", "montserrat", "source-sans-3", "ibm-plex-sans", "nunito-sans", "roboto"] as const;
export type FontId = (typeof FONT_IDS)[number];

export interface PaletteInput {
  primary: string;
  accent: string;
  tint: string;
  heading: FontId;
  body: FontId;
}

export type TokenMap = Record<string, string>;
export interface Palette {
  light: TokenMap;
  dark: TokenMap;
  fonts: TokenMap;
}

export const FONT_FAMILIES: Record<FontId, string> = {
  inter: "Inter",
  montserrat: "Montserrat",
  "source-sans-3": "Source Sans 3",
  "ibm-plex-sans": "IBM Plex Sans",
  "nunito-sans": "Nunito Sans",
  roboto: "Roboto",
};

/** Every colour custom property a palette sets, in both modes. */
export const COLOR_TOKENS = [
  "--surface-primary", "--surface-secondary", "--surface-tertiary", "--surface-selected", "--surface-raised", "--surface-chat",
  "--text-primary", "--text-secondary", "--text-tertiary", "--text-quaternary",
  "--border-default", "--border-heavy", "--border-subtle",
  "--brand-primary", "--brand-primary-hover", "--brand-primary-text", "--ring", "--brand-accent",
  "--ink-solid", "--ink-solid-hover", "--ink-solid-text",
  "--sidebar-bg", "--sidebar-hover", "--sidebar-active", "--user-bubble-bg", "--conversation-body-color",
] as const;

type Rgb = readonly [number, number, number];

const WHITE: Rgb = [255, 255, 255];
const BLACK: Rgb = [0, 0, 0];
const CHARCOAL: Rgb = [0x1a, 0x1a, 0x1a];
const HEX = /^#[0-9A-Fa-f]{6}$/;

const parse = (hex: string): Rgb => [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16)) as unknown as Rgb;
const hex = (color: Rgb) => "#" + color.map((channel) => channel.toString(16).padStart(2, "0")).join("").toUpperCase();
const rgba = (color: Rgb, alpha: string) => `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;

// a + (b - a) * pct / 100 per channel, rounded half up, on integers only.
const mix = (a: Rgb, b: Rgb, pct: number): Rgb =>
  a.map((x, index) => Math.floor((2 * (x * (100 - pct) + b[index]! * pct) + 100) / 200)) as unknown as Rgb;

function luminance(color: Rgb): number {
  const [r, g, b] = color.map((value) => {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

/** WCAG contrast of two `#RRGGBB` strings (callers validate the shape first). */
export const contrastOfHex = (first: string, second: string): number => contrast(parse(first), parse(second));

// First 5% step from `color` toward `toward` that reaches `target` contrast against `against`.
function search(color: Rgb, toward: Rgb, against: Rgb, target: number): Rgb | null {
  for (let pct = 0; pct <= 100; pct += 5) {
    const candidate = mix(color, toward, pct);
    if (contrast(candidate, against) >= target) return candidate;
  }
  return null;
}

const stack = (id: FontId) => `"${FONT_FAMILIES[id]}", "Segoe UI", system-ui, -apple-system, sans-serif`;
const readable = (text: Rgb, surface: Rgb, ratio: number) => contrast(text, surface) >= ratio;

function tokens(values: readonly string[]): TokenMap {
  return Object.fromEntries(COLOR_TOKENS.map((name, index) => [name, values[index]!]));
}

export function generatePalette(input: PaletteInput): Palette | null {
  if (typeof input !== "object" || input === null) return null;
  const { primary, accent, tint, heading, body } = input;
  if (![primary, accent, tint].every((color) => typeof color === "string" && HEX.test(color))) return null;
  if (!FONT_IDS.includes(heading) || !FONT_IDS.includes(body)) return null;
  const p = parse(primary);
  const a = parse(accent);
  const t = parse(tint);

  // Knob feasibility: primary and accent need 3:1 on white, the tint must carry charcoal text.
  if (contrast(p, WHITE) < 3 || contrast(a, WHITE) < 3 || contrast(CHARCOAL, t) < 7) return null;

  const lightSecondary = mix(WHITE, t, 20);
  const lightTertiary = mix(WHITE, t, 40);
  const text2 = parse("#4A4F52");
  const text3 = parse("#656A6D");
  const text4 = parse("#8A8E90");
  if (contrast(text3, lightTertiary) < 4.5) return null;
  const lightBrand = search(p, BLACK, lightTertiary, 4.5);
  if (!lightBrand) return null;
  const lightInk = mix(lightBrand, BLACK, 70);
  for (const surface of [WHITE, lightSecondary]) {
    if (!readable(CHARCOAL, surface, 7) || !readable(text2, surface, 4.5) || !readable(text3, surface, 4.5) || !readable(lightBrand, surface, 4.5)) return null;
  }
  if (!readable(WHITE, lightBrand, 4.5) || !readable(WHITE, lightInk, 7)) return null;

  const light = tokens([
    "#FFFFFF", hex(lightSecondary), hex(lightTertiary), hex(t), hex(mix(WHITE, t, 30)), "#FFFFFF",
    hex(CHARCOAL), hex(text2), hex(text3), hex(text4),
    hex(mix(WHITE, t, 60)), hex(mix(t, BLACK, 8)), "rgba(26, 26, 26, 0.08)",
    hex(lightBrand), hex(mix(lightBrand, BLACK, 20)), "#FFFFFF", hex(lightBrand), hex(a),
    hex(lightInk), hex(mix(lightBrand, BLACK, 50)), "#FFFFFF",
    hex(mix(WHITE, t, 25)), hex(mix(WHITE, t, 50)), hex(t), hex(mix(WHITE, t, 22)), hex(CHARCOAL),
  ]);

  const base = mix(p, BLACK, 85);
  const darkSecondary = mix(p, BLACK, 78);
  const darkTertiary = mix(p, BLACK, 72);
  const darkText = mix(t, WHITE, 30);
  const darkText2 = mix(darkText, base, 25);
  const darkText3 = mix(darkText, base, 45);
  const darkText4 = mix(darkText, base, 60);
  const darkBrand = search(p, WHITE, darkTertiary, 4.5);
  const darkAccent = search(a, WHITE, base, 3);
  if (!darkBrand || !darkAccent) return null;
  for (const surface of [base, darkSecondary]) {
    if (!readable(darkText, surface, 7) || !readable(darkText2, surface, 4.5) || !readable(darkText3, surface, 4.5) || !readable(darkBrand, surface, 4.5)) return null;
  }
  if (!readable(base, darkBrand, 4.5) || !readable(base, darkText, 7)) return null;

  const dark = tokens([
    hex(base), hex(darkSecondary), hex(darkTertiary), hex(mix(p, BLACK, 62)), hex(mix(p, BLACK, 75)), hex(base),
    hex(darkText), hex(darkText2), hex(darkText3), hex(darkText4),
    hex(mix(darkTertiary, darkText, 12)), hex(mix(darkTertiary, darkText, 22)), rgba(t, "0.08"),
    hex(darkBrand), hex(mix(darkBrand, WHITE, 20)), hex(base), hex(darkBrand), hex(darkAccent),
    hex(darkText), hex(mix(darkText, WHITE, 30)), hex(base),
    hex(mix(p, BLACK, 90)), rgba(t, "0.06"), rgba(t, "0.10"), hex(darkSecondary), hex(darkText),
  ]);

  return { light, dark, fonts: { "--font-heading": stack(heading), "--font-body": stack(body) } };
}
