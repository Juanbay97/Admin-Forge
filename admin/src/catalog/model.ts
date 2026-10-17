import { ApiError } from "../api/client";
import { t } from "../i18n/config";
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
  if (selected.length === 0) return { ok: false, problems: [t("catalog.validation.selectOne")] };

  const problems: string[] = [];
  const seen = new Set<string>();
  const repeated = new Set<string>();
  for (const { alias } of selected) {
    if (!ALIAS_PATTERN.test(alias)) {
      problems.push(t("catalog.validation.aliasFormat", { alias }));
    }
    if (seen.has(alias) && !repeated.has(alias)) {
      repeated.add(alias);
      problems.push(t("catalog.validation.aliasRepeated", { alias }));
    }
    seen.add(alias);
  }
  const chosen = selected.find((row) => row.upstream === defaultUpstream);
  if (!chosen) problems.push(t("catalog.validation.chooseDefault"));
  if (problems.length > 0 || !chosen) return { ok: false, problems };
  return {
    ok: true,
    aliases: Object.fromEntries(selected.map((row) => [row.alias, row.upstream])),
    defaultAlias: chosen.alias,
  };
}

export const publicationLabel = (state: PublicationState) => t(`catalog.publication.${state}`);

export type CatalogAction = "load" | "refresh" | "publish";

/** Server detail is never shown: messages are fixed, redacted and say what to do next. */
export function describeCatalogFailure(failure: unknown, action: CatalogAction): string {
  const error = failure instanceof ApiError ? failure : null;
  if (action === "publish" && error?.code === "REVISION_CONFLICT") {
    return t("catalog.failure.conflict");
  }
  if (action === "publish" && error?.code === "MODEL_NOT_ALLOWED") {
    return t("catalog.failure.notAllowed");
  }
  if (action === "publish" && error?.status === 422) {
    return t("catalog.failure.rejected");
  }
  if (action === "refresh") return t("catalog.failure.refresh");
  return action === "load" ? t("catalog.failure.load") : t("catalog.failure.publish");
}