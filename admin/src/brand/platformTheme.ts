// The platform area never takes a company's look: it always applies this fixed Prometheon theme, with the bundled
// marks only, through the same validated applier the company themes use. Entering the area overwrites every
// `--brand-*` variable a company theme set earlier in the session.
import type { StyleTarget } from "./applier";
import { applyBrandTheme, defaultTheme, type BrandTheme } from "./theme";

export const platformTheme: BrandTheme = Object.freeze({
  ...defaultTheme,
  name: "Prometheon Forge",
  title: "Prometheon Forge Platform",
});

export function applyPlatformTheme(root?: StyleTarget): boolean {
  return applyBrandTheme(platformTheme, root);
}
