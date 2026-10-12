// The branding record as the control plane serves it, plus the editable draft the admin works on.
// Everything that arrives from the network goes through `parseBranding`, which accepts the exact shape or
// throws; nothing here builds CSS or markup from it.

import { ApiError } from "../api/client";
import { contrastOfHex, FONT_IDS, generatePalette, type FontId, type PaletteInput } from "./palette";

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
  exact(top, TOP_KEYS, "document");
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

const UNREADABLE =
  "These colors cannot produce a readable theme in the apps: the accent needs 3:1 contrast on white and the background tint must carry dark text. Adjust them to save.";

/**
 * The server is the authority on syntax and on the primary color's contrast, so those drafts go through
 * and its error is shown. What the server cannot judge is whether the apps can derive a readable palette;
 * a draft the server would accept but the generator refuses is blocked here, since the apps would silently
 * ignore it.
 */
export function saveBlocker(draft: Draft): string | null {
  if (![draft.primary, draft.accent, draft.tint].every((color) => HEX.test(color))) return null;
  if (contrastOfHex(draft.primary, "#FFFFFF") < MIN_PRIMARY_CONTRAST) return null;
  return generatePalette(draftTheme(draft)) ? null : UNREADABLE;
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
      return "The branding was changed by another administrator. Reload to see the latest version; nothing was overwritten.";
    }
    if (error.status === 0) return error.message;
    if (error.status === 429) return "Too many requests. Wait a moment and try again.";
    if (error.status === 404) return "Branding is not available for this organization.";
    if (SERVER_AUTHORED.has(error.code) && error.status >= 400 && error.status < 500) return error.message;
  }
  return "Something went wrong. Try again.";
}