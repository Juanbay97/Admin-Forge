import { ApiError } from "../api/client";
import type { PublicationState } from "../api/catalog";

export const ALIAS_PATTERN = /^[a-z][a-z0-9_-]{0,63}$/;
const ALIAS_MAX = 64;

/** One discovered upstream model and how the admin wants to publish it. */
export interface Row {
  upstream: string;
  selected: boolean;
  alias: string;
}

export type Selection =
  | { ok: true; aliases: Record<string, string>; defaultAlias: string }
  | { ok: false; problems: string[] };

/** Normalise an upstream id into the alias grammar (a letter first, lowercase, `-`/`_`/digits). */
export function suggestAlias(upstream: string): string {
  const slug = upstream
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (/^[a-z]/.test(slug) ? slug : `m-${slug}`).slice(0, ALIAS_MAX);
}

export const initialRows = (ids: string[]): Row[] =>
  ids.map((upstream) => ({ upstream, selected: true, alias: suggestAlias(upstream) }));

/** The chosen default, or the first selected row once the chosen one is dropped. */
export function effectiveDefault(rows: Row[], preferred: string): string {
  const selected = rows.filter((row) => row.selected);
  return selected.some((row) => row.upstream === preferred) ? preferred : (selected[0]?.upstream ?? "");
}

export function validateSelection(rows: Row[], defaultUpstream: string): Selection {
  const selected = rows.filter((row) => row.selected);
  if (selected.length === 0) return { ok: false, problems: ["Select at least one model."] };

  const problems: string[] = [];
  const seen = new Set<string>();
  const repeated = new Set<string>();
  for (const { alias } of selected) {
    if (!ALIAS_PATTERN.test(alias)) {
      problems.push(`Alias "${alias}" must start with a letter and use only lowercase letters, digits, "-" and "_".`);
    }
    if (seen.has(alias) && !repeated.has(alias)) {
      repeated.add(alias);
      problems.push(`Alias "${alias}" is used more than once.`);
    }
    seen.add(alias);
  }
  const chosen = selected.find((row) => row.upstream === defaultUpstream);
  if (!chosen) problems.push("Choose a default model.");
  if (problems.length > 0 || !chosen) return { ok: false, problems };
  return {
    ok: true,
    aliases: Object.fromEntries(selected.map((row) => [row.alias, row.upstream])),
    defaultAlias: chosen.alias,
  };
}

export const publicationLabel = (state: PublicationState) =>
  ({ CURRENT: "Published", UNPUBLISHED: "Not published", STALE_GATEWAY: "Gateway changed since publishing" })[state];

export type CatalogAction = "load" | "refresh" | "publish";

/** Server detail is never shown: messages are fixed, redacted and say what to do next. */
export function describeCatalogFailure(failure: unknown, action: CatalogAction): string {
  const error = failure instanceof ApiError ? failure : null;
  if (action === "publish" && error?.code === "REVISION_CONFLICT") {
    return "The catalog or gateway changed since the models were refreshed. Refresh the models and try again.";
  }
  if (action === "publish" && error?.status === 422) {
    return "The selection was not accepted. Refresh the models, then check the aliases.";
  }
  if (action === "refresh") return "The gateway could not be reached. Check the gateway settings, then try again.";
  return action === "load" ? "The catalog could not be loaded. Try again." : "The catalog could not be published. Try again.";
}