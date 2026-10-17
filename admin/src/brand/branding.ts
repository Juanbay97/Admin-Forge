// The branding record as the control plane serves it, plus the editable draft the admin works on.
// Everything that arrives from the network goes through `parseBranding`, which accepts the exact shape or
// throws; nothing here builds CSS or markup from it.

import { ApiError } from "../api/client";
import { t } from "../i18n/config";
import { FONT_IDS, contrastOfHex, generatePalette, type FontId, type PaletteInput } from "./palette";

export const ASSET_URL_PREFIX = "/forge/v1/branding/assets/";
export const ASSET_KINDS = ["logoLight", "logoDark", "isotipo"] as const;
export type AssetKind = (typeof ASSET_KINDS)[number];
export const NAME_MAX = 40;
export const LOGIN_COPY_MAX = 280;
export const MIN_PRIMARY_CONTRAST = 3;

export interface Branding {
  revision: number;
  name: string;
  loginCopy: string;
  theme: PaletteInput;
  /** Same-origin content-addressed URLs, `/forge/v1/branding/assets/<sha256>`. */
  assets: Partial<Record<AssetKind, string>>;
  /** The company code employees type. Only the authenticated read carries it; save and reset answers do not. */
  code?: string;
}

/** Mirrors `forge.branding.DEFAULT`: the Prometheon look at revision 0. */
export const DEFAULT_BRANDING: Branding = {
  revision: 0,
  name: "Prometheon Forge",
  loginCopy: "Sign in to your Forge workspace.",
  theme: { primary: "#0B1D26", accent: "#E07A2D", tint: "#E8DCC1", heading: "montserrat", body: "inter" },
  assets: {},
};

const HEX = /^#[0-9A-Fa-f]{6}$/;
const ASSET_URL = new RegExp(`^${ASSET_URL_PREFIX.replace(/\//g, "\\/")}[0-9a-f]{64}$`);
// C0/C1 controls, line/paragraph separators, BOM, bidirectional marks, and the markup/CSS structure characters.
const FORBIDDEN_TEXT = /[\u0000-\u001F\u007F-\u009F\u061C\u200E\u200F\u2028\u2029\u202A-\u202E\u2066-\u2069\uFEFF<>{}`\\]/;

const THEME_KEYS = ["primary", "accent", "tint", "heading", "body"];
const TOP_KEYS = ["revision", "name", "loginCopy", "theme", "assets"];
const COMPANY_CODE = /^[a-z0-9][a-z0-9-]{0,62}$/;

export class BrandingParseError extends Error {
  constructor(readonly field: string) {
    super(`The branding response is invalid (${field}).`);
    this.name = "BrandingParseError";
  }
}

function record(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new BrandingParseError(field);
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) throw new BrandingParseError(field);
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, keys: readonly string[], field: string, optional = false): void {
  const present = Object.keys(value);
  if (present.some((key) => !keys.includes(key))) throw new BrandingParseError(field);
  if (!optional && keys.some((key) => !present.includes(key))) throw new BrandingParseError(field);
}

function text(value: unknown, min: number, max: number, field: string): string {
  if (typeof value !== "string" || FORBIDDEN_TEXT.test(value)) throw new BrandingParseError(field);
  const length = [...value].length;
  if (length > max || value.trim().length < min) throw new BrandingParseError(field);
  return value;
}

export function parseBranding(raw: unknown): Branding {
  const top = record(raw, "document");
  exact(top, [...TOP_KEYS, "code"], "document", true);
  if (TOP_KEYS.some((key) => !(key in top))) throw new BrandingParseError("document");
  if ("code" in top && (typeof top.code !== "string" || !COMPANY_CODE.test(top.code))) throw new BrandingParseError("code");
  const { revision } = top;
  if (typeof revision !== "number" || !Number.isInteger(revision) || revision < 0 || revision > 2 ** 53 - 1) {
    throw new BrandingParseError("revision");
  }
  const theme = record(top.theme, "theme");
  exact(theme, THEME_KEYS, "theme");
  for (const key of ["primary", "accent", "tint"]) {
    if (typeof theme[key] !== "string" || !HEX.test(theme[key])) throw new BrandingParseError(`theme.${key}`);
  }
  for (const key of ["heading", "body"]) {
    if (typeof theme[key] !== "string" || !(FONT_IDS as readonly string[]).includes(theme[key])) {
      throw new BrandingParseError(`theme.${key}`);
    }
  }
  const assets = record(top.assets, "assets");
  exact(assets, ASSET_KINDS, "assets", true);
  const checked: Partial<Record<AssetKind, string>> = {};
  for (const kind of ASSET_KINDS) {
    if (!(kind in assets)) continue;
    const url = assets[kind];
    if (typeof url !== "string" || !ASSET_URL.test(url)) throw new BrandingParseError(`assets.${kind}`);
    checked[kind] = url;
  }
  return {
    revision,
    name: text(top.name, 1, NAME_MAX, "name"),
    loginCopy: text(top.loginCopy, 0, LOGIN_COPY_MAX, "loginCopy"),
    theme: {
      primary: (theme.primary as string).toUpperCase(),
      accent: (theme.accent as string).toUpperCase(),
      tint: (theme.tint as string).toUpperCase(),
      heading: theme.heading as FontId,
      body: theme.body as FontId,
    },
    assets: checked,
    ...(typeof top.code === "string" ? { code: top.code } : {}),
  };
}

/** What the form edits: plain strings (possibly invalid) and uploaded asset hashes. */
export interface Draft {
  name: string;
  loginCopy: string;
  primary: string;
  accent: string;
  tint: string;
  heading: FontId;
  body: FontId;
  assets: Partial<Record<AssetKind, string>>;
}

export const assetHash = (url: string): string => url.slice(ASSET_URL_PREFIX.length);

export function draftFrom(branding: Branding): Draft {
  const assets: Draft["assets"] = {};
  for (const kind of ASSET_KINDS) {
    const url = branding.assets[kind];
    if (url !== undefined) assets[kind] = assetHash(url);
  }
  return { name: branding.name, loginCopy: branding.loginCopy, ...branding.theme, assets };
}

/** The body the server expects for a save, sent exactly as typed: the server validates and normalises. */
export function draftToDocument(draft: Draft) {
  return {
    name: draft.name,
    loginCopy: draft.loginCopy,
    theme: { primary: draft.primary, accent: draft.accent, tint: draft.tint, heading: draft.heading, body: draft.body },
    assets: { ...draft.assets },
  };
}

export const draftTheme = (draft: Draft): PaletteInput => ({
  primary: draft.primary,
  accent: draft.accent,
  tint: draft.tint,
  heading: draft.heading,
  body: draft.body,
});

// There is no client-side save gate: the control plane runs the same palette generator and answers with
// its own message, which is what the page shows after Save. `paletteIssues` runs that same generator while
// you type so the problem is visible earlier; it never blocks a save and the server stays the authority.

export type PaletteIssues = Partial<Record<"primary" | "accent" | "tint" | "combination", string>>;

const DARK_TEXT = "#1A1A1A";

/** What stops the three colors from forming a readable theme, keyed by the field to fix. Empty when readable. */
export function paletteIssues(draft: Draft): PaletteIssues {
  const issues: PaletteIssues = {};
  for (const key of ["primary", "accent", "tint"] as const) {
    if (!HEX.test(draft[key])) issues[key] = t("branding.issues.hex", { color: t(`branding.colorNames.${key}`) });
  }
  if (Object.keys(issues).length > 0) return issues;
  if (generatePalette(draftTheme(draft)) !== null) return issues;
  for (const key of ["primary", "accent"] as const) {
    if (contrastOfHex(draft[key], "#FFFFFF") < 3) {
      issues[key] = t("branding.issues.contrast", { color: t(`branding.colorNames.${key}`) });
    }
  }
  if (contrastOfHex(DARK_TEXT, draft.tint) < 7) {
    issues.tint = t("branding.issues.darkText");
  }
  if (Object.keys(issues).length === 0) {
    issues.combination = t("branding.issues.combination");
  }
  return issues;
}
export function isDefaultLook(theme: PaletteInput): boolean {
  const base = DEFAULT_BRANDING.theme;
  return (
    theme.primary.toUpperCase() === base.primary &&
    theme.accent.toUpperCase() === base.accent &&
    theme.tint.toUpperCase() === base.tint &&
    theme.heading === base.heading &&
    theme.body === base.body
  );
}

const SERVER_AUTHORED = new Set(["INVALID_REQUEST", "PAYLOAD_TOO_LARGE", "UNSUPPORTED_MEDIA_TYPE"]);

/** User-facing text for a failed branding call. Only the control plane's own refusal messages are shown verbatim. */
export function describeBrandingFailure(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "REVISION_CONFLICT") {
      return t("branding.failure.conflict");
    }
    if (error.status === 0) return t("errors.NETWORK");
    if (error.status === 429) return t("branding.failure.rateLimited");
    if (error.status === 404) return t("branding.failure.notAvailable");
    if (SERVER_AUTHORED.has(error.code) && error.status >= 400 && error.status < 500) return error.message;
  }
  return t("errors.generic");
}