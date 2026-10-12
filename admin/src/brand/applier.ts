// The only way theme values reach the page: CSSOM `style.setProperty` on an element, never CSS text.
// Defence in depth on top of the typed model: every value must be a plain colour literal or a font
// family list, and every name a custom property, otherwise nothing at all is written.

export interface StyleTarget {
  style: { setProperty(name: string, value: string): void; removeProperty?(name: string): string };
}

const SAFE_COLOR = /^(#[0-9A-Fa-f]{6}|rgba\(\d{1,3}, \d{1,3}, \d{1,3}, (?:0|1|0?\.\d+)\))$/;
const FONT_ITEM = '(?:"[A-Za-z0-9 ]+"|-?[a-z][a-z-]*)';
const SAFE_FONT = new RegExp(`^${FONT_ITEM}(?:, ${FONT_ITEM})*$`);
const SAFE_NAME = /^--[a-z0-9-]+$/;
const isFontVariable = (name: string) => /^--(?:brand-)?font-/.test(name);

export function isSafeVariable(name: string, value: unknown): boolean {
  if (!SAFE_NAME.test(name) || typeof value !== "string") return false;
  return (isFontVariable(name) ? SAFE_FONT : SAFE_COLOR).test(value);
}

/** Writes every variable, or none when any one is unsafe. */
export function applyVariables(target: StyleTarget, variables: Record<string, string>): boolean {
  const entries = Object.entries(variables);
  if (!entries.every(([name, value]) => isSafeVariable(name, value))) return false;
  for (const [name, value] of entries) target.style.setProperty(name, value);
  return true;
}
