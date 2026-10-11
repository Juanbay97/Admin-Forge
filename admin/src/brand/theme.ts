// One typed theme object feeds the CSS variables Tailwind reads; per-company theming
// later means supplying another object, never editing a component.
export interface BrandTheme {
  name: string;
  colors: { primary: string; teal: string; accent: string; sand: string; carbon: string };
  fonts: { title: string; body: string };
  assets: { markOnLight: string; markOnDark: string };
}

export const defaultTheme: BrandTheme = {
  name: "Prometheon Forge",
  colors: { primary: "#0B1D26", teal: "#0F6B6D", accent: "#E07A2D", sand: "#E8DCC1", carbon: "#1A1A1A" },
  fonts: { title: "Montserrat", body: "Inter" },
  assets: { markOnLight: "/admin/brand/isotipo_claro.png", markOnDark: "/admin/brand/isotipo_oscuro.png" },
};

export interface ThemeOverrides {
  name?: string;
  colors?: Partial<BrandTheme["colors"]>;
  fonts?: Partial<BrandTheme["fonts"]>;
  assets?: Partial<BrandTheme["assets"]>;
}

export function createTheme(overrides: ThemeOverrides): BrandTheme {
  return {
    name: overrides.name ?? defaultTheme.name,
    colors: { ...defaultTheme.colors, ...overrides.colors },
    fonts: { ...defaultTheme.fonts, ...overrides.fonts },
    assets: { ...defaultTheme.assets, ...overrides.assets },
  };
}

interface StyleRoot {
  style: { setProperty(name: string, value: string): void };
}

const fontStack = (family: string) => `"${family}", system-ui, sans-serif`;

export function applyBrandTheme(theme: BrandTheme, root: StyleRoot = document.documentElement): void {
  const { colors, fonts } = theme;
  const variables: Record<string, string> = {
    "--brand-primary": colors.primary,
    "--brand-teal": colors.teal,
    "--brand-accent": colors.accent,
    "--brand-sand": colors.sand,
    "--brand-carbon": colors.carbon,
    "--brand-font-title": fontStack(fonts.title),
    "--brand-font-body": fontStack(fonts.body),
  };
  for (const [name, value] of Object.entries(variables)) root.style.setProperty(name, value);
}