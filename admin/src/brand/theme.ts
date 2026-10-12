// One typed theme object feeds the CSS variables Tailwind reads; per-company theming
// means supplying another object (`themeFromBranding`), never editing a component.
import { applyVariables, type StyleTarget } from "./applier";
import { ASSET_URL_PREFIX, isDefaultLook, type Branding } from "./branding";
import { FONT_FAMILIES, generatePalette } from "./palette";

export interface BrandTheme {
  name: string;
  /** Document title. */
  title: string;
  /** Favicon URL: a bundled file or a same-origin content-addressed logo. */
  favicon: string;
  colors: { primary: string; teal: string; accent: string; sand: string; carbon: string };
  fonts: { title: string; body: string };
  assets: { markOnLight: string; markOnDark: string };
}

export const defaultTheme: BrandTheme = {
  name: "Prometheon Forge",
  title: "Prometheon Forge Admin",
  favicon: "/admin/brand/isotipo_claro.png",
  colors: { primary: "#0B1D26", teal: "#0F6B6D", accent: "#E07A2D", sand: "#E8DCC1", carbon: "#1A1A1A" },
  fonts: { title: "Montserrat", body: "Inter" },
  assets: { markOnLight: "/admin/brand/isotipo_claro.png", markOnDark: "/admin/brand/isotipo_oscuro.png" },
};

export interface ThemeOverrides {
  name?: string;
  title?: string;
  favicon?: string;
  colors?: Partial<BrandTheme["colors"]>;
  fonts?: Partial<BrandTheme["fonts"]>;
  assets?: Partial<BrandTheme["assets"]>;
}

export function createTheme(overrides: ThemeOverrides): BrandTheme {
  return {
    name: overrides.name ?? defaultTheme.name,
    title: overrides.title ?? defaultTheme.title,
    favicon: overrides.favicon ?? defaultTheme.favicon,
    colors: { ...defaultTheme.colors, ...overrides.colors },
    fonts: { ...defaultTheme.fonts, ...overrides.fonts },
    assets: { ...defaultTheme.assets, ...overrides.assets },
  };
}

/**
 * The admin shell theme of a branding record. The Prometheon default knobs keep the shipped look exactly;
 * any other knobs map from the generated light palette (ink header, brand navigation, accent, tint
 * background, text). Knobs the palette cannot express fall back to the default colours.
 */
export function themeFromBranding(branding: Branding): BrandTheme {
  const { name, assets } = branding;
  const palette = isDefaultLook(branding.theme) ? null : generatePalette(branding.theme);
  const colors = palette
    ? {
        primary: palette.light["--ink-solid"]!,
        teal: palette.light["--brand-primary"]!,
        accent: palette.light["--brand-accent"]!,
        sand: palette.light["--surface-selected"]!,
        carbon: palette.light["--text-primary"]!,
      }
    : defaultTheme.colors;
  const expressible = palette !== null || isDefaultLook(branding.theme);
  const fonts = expressible
    ? { title: FONT_FAMILIES[branding.theme.heading], body: FONT_FAMILIES[branding.theme.body] }
    : defaultTheme.fonts;
  // A missing variant borrows the other logo, then the isotipo, then the bundled Prometheon art.
  return {
    name,
    title: `${name} Admin`,
    favicon: assets.isotipo ?? assets.logoLight ?? defaultTheme.favicon,
    colors,
    fonts,
    assets: {
      markOnLight: assets.logoLight ?? assets.isotipo ?? defaultTheme.assets.markOnLight,
      markOnDark: assets.logoDark ?? assets.logoLight ?? assets.isotipo ?? defaultTheme.assets.markOnDark,
    },
  };
}

const fontStack = (family: string) => `"${family}", system-ui, sans-serif`;

export function applyBrandTheme(theme: BrandTheme, root: StyleTarget = document.documentElement): boolean {
  const { colors, fonts } = theme;
  return applyVariables(root, {
    "--brand-primary": colors.primary,
    "--brand-teal": colors.teal,
    "--brand-accent": colors.accent,
    "--brand-sand": colors.sand,
    "--brand-carbon": colors.carbon,
    "--brand-font-title": fontStack(fonts.title),
    "--brand-font-body": fontStack(fonts.body),
  });
}

interface IdentityTarget {
  title: string;
  querySelector(selector: string): { setAttribute(name: string, value: string): void } | null;
}

const SAFE_ICON = new RegExp(`^(?:/admin/brand/[A-Za-z0-9_.-]+\\.png|${ASSET_URL_PREFIX.replace(/\//g, "\\/")}[0-9a-f]{64})$`);

/** Document title and favicon: text and a same-origin path only. Returns false when the favicon is refused. */
export function applyBrandIdentity(theme: BrandTheme, doc: IdentityTarget = document): boolean {
  doc.title = theme.title;
  const link = doc.querySelector('link[rel="icon"]');
  if (!link || !SAFE_ICON.test(theme.favicon)) return false;
  link.setAttribute("href", theme.favicon);
  return true;
}
