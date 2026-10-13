import type { Company } from "../api/platform";

export type StatusFilter = "all" | "active" | "suspended";

export const parseStatus = (value: string | null): StatusFilter => (value === "active" || value === "suspended" ? value : "all");

export function filterCompanies<T extends Pick<Company, "slug" | "display_name" | "active">>(companies: readonly T[], { q, status }: { q: string; status: StatusFilter }): T[] {
  const needle = q.trim().toLowerCase();
  return companies.filter(
    (company) =>
      (status === "all" || (status === "active") === company.active) &&
      (!needle || company.display_name.toLowerCase().includes(needle) || company.slug.toLowerCase().includes(needle)),
  );
}

/** The wizard's rule (3 to 32 characters) inside the server's (`[a-z0-9][a-z0-9-]{0,62}`). */
export const isCompanyCode = (value: string): boolean => /^[a-z0-9][a-z0-9-]{2,31}$/.test(value);

/** A readable starting point for the code: ASCII letters and digits, single hyphens, at most 32 characters. */
export function slugFromName(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32)
    .replace(/-+$/g, "");
}

export interface Checklist {
  branding: boolean;
  keys: boolean;
  models: boolean;
  /** A company can work once it has a gateway key and models; branding is a choice. */
  complete: boolean;
}

export function setupChecklist({ brandingRevision, keyCount, modelCount }: { brandingRevision: number; keyCount: number; modelCount: number }): Checklist {
  const keys = keyCount > 0;
  const models = modelCount > 0;
  return { branding: brandingRevision > 0, keys, models, complete: keys && models };
}