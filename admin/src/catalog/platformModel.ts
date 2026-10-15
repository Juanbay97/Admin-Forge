import type { KeyDiscoveryState } from "../api/platform";
import { ApiError } from "../api/client";
import { suggestAlias, type Row } from "./model";

/** How each finite per-key discovery outcome reads: a label, a tone and what to do about it. Never an upstream message. */
export const KEY_STATES: Record<KeyDiscoveryState, { label: string; tone: "success" | "warning" | "destructive" | "neutral"; hint: string }> = {
  ok: { label: "Reachable", tone: "success", hint: "" },
  unreachable: { label: "Not reachable", tone: "destructive", hint: "The gateway did not answer for this key. Check the key and its origin, then discover again." },
  unreadable: { label: "Cannot be read", tone: "destructive", hint: "The stored key could not be opened. Rotate it in the Keys tab." },
  no_key: { label: "No key stored", tone: "warning", hint: "This key is a placeholder. Rotate it in the Keys tab to store the key." },
  disabled: { label: "Disabled", tone: "warning", hint: "Enable the key in the Keys tab to use it." },
  inactive: { label: "Assigned but off", tone: "neutral", hint: "The assignment is switched off in the Keys tab." },
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
  if (error?.code === "MFA_REQUIRED") return "Two-factor verification is required. Verify it is you, then try again.";
  if (action === "publish" && error?.code === "REVISION_CONFLICT") return "The catalog or the keys changed since the models were discovered. Discover the models again, then publish.";
  if (action === "publish" && error?.code === "NO_ACTIVE_MEMBER") return "This company has no active member yet. Publishing needs one person who has joined.";
  if (action === "publish" && error?.status === 422) return "The selection was not accepted. Discover the models again, then check the aliases.";
  if (action === "discover") return "Discovery could not be completed. Try again shortly.";
  return action === "load" ? "The catalog could not be loaded. Try again." : "The catalog could not be published. Try again.";
}
