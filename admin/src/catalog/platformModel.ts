import type { KeyDiscoveryState } from "../api/platform";
import { ApiError } from "../api/client";
import { t } from "../i18n/config";
import { suggestAlias, type Row } from "./model";

type KeyStateView = { readonly label: string; readonly tone: "success" | "warning" | "destructive" | "neutral"; readonly hint: string };

/** How each finite per-key discovery outcome reads: a label, a tone and what to do about it, in the active language. Never an upstream message. */
export const KEY_STATES: Record<KeyDiscoveryState, KeyStateView> = {
  ok: { tone: "success", get label() { return t("catalog.keyStates.ok.label"); }, hint: "" },
  unreachable: { tone: "destructive", get label() { return t("catalog.keyStates.unreachable.label"); }, get hint() { return t("catalog.keyStates.unreachable.hint"); } },
  unreadable: { tone: "destructive", get label() { return t("catalog.keyStates.unreadable.label"); }, get hint() { return t("catalog.keyStates.unreadable.hint"); } },
  no_key: { tone: "warning", get label() { return t("catalog.keyStates.no_key.label"); }, get hint() { return t("catalog.keyStates.no_key.hint"); } },
  disabled: { tone: "warning", get label() { return t("catalog.keyStates.disabled.label"); }, get hint() { return t("catalog.keyStates.disabled.hint"); } },
  inactive: { tone: "neutral", get label() { return t("catalog.keyStates.inactive.label"); }, get hint() { return t("catalog.keyStates.inactive.hint"); } },
};

/** One row per discovered model. The published selection comes back preselected under its published aliases; nothing else is. */
export function buildRows(ids: string[], published: Record<string, string>): Row[] {
  const aliasOf = new Map<string, string>();
  for (const [alias, upstream] of Object.entries(published)) if (!aliasOf.has(upstream)) aliasOf.set(upstream, alias);
  return [...ids].sort().map((upstream) => {
    const alias = aliasOf.get(upstream);
    return { upstream, selected: alias !== undefined, alias: alias ?? suggestAlias(upstream) };
  });
}

/** The upstream model the published default alias points at, or "" when nothing is published. */
export function preferredDefault(published: Record<string, string>, defaultAlias: string | null): string {
  return defaultAlias ? (published[defaultAlias] ?? "") : "";
}

/** A fresh discovery keeps every edit made so far, adds new models unselected and drops those the gateway no longer serves. */
export function mergeDiscovery(previous: Row[], ids: string[]): Row[] {
  const known = new Map(previous.map((row) => [row.upstream, row]));
  return [...ids].sort().map((upstream) => known.get(upstream) ?? { upstream, selected: false, alias: suggestAlias(upstream) });
}

/** Case-insensitive match on the model id or its alias. */
export function filterRows(rows: Row[], query: string): Row[] {
  const needle = query.trim().toLowerCase();
  return needle ? rows.filter((row) => row.upstream.toLowerCase().includes(needle) || row.alias.toLowerCase().includes(needle)) : rows;
}

export type PlatformCatalogAction = "load" | "discover" | "publish";

/** Fixed, redacted copy that says what to do next; the server's free text is never shown. */
export function describeCatalogFailure(failure: unknown, action: PlatformCatalogAction): string {
  const error = failure instanceof ApiError ? failure : null;
  if (error?.code === "MFA_REQUIRED") return t("catalog.platformFailure.mfa");
  if (action === "publish" && error?.code === "REVISION_CONFLICT") return t("catalog.platformFailure.conflict");
  if (action === "publish" && error?.code === "NO_ACTIVE_MEMBER") return t("catalog.platformFailure.noActiveMember");
  if (action === "publish" && error?.status === 422) return t("catalog.platformFailure.rejected");
  if (action === "discover") return t("catalog.platformFailure.discover");
  return action === "load" ? t("catalog.failure.load") : t("catalog.failure.publish");
}
