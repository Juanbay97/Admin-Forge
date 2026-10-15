import type { AuditEntry } from "../api/platform";
import { formatDate } from "../lib/format";

const LABELS: Record<string, string> = {
  "company.created": "Company created",
  "company.suspended": "Company suspended",
  "company.reactivated": "Company reactivated",
  "company.branding_saved": "Branding saved",
  "company.gateway_assigned": "Gateway keys assigned",
  "company.model_access_set": "Model access set",
  "gateway_key.created": "Gateway key added",
  "gateway_key.rotated": "Gateway key rotated",
  "gateway_key.status_changed": "Gateway key enabled or disabled",
  "company.models_discovered": "Models discovered",
  "company.catalog_published": "Catalog published",
  "model_price.set": "Model price set",
  "owner.mfa_enrolled": "Second factor enrolled",
  "owner.mfa_recovery_used": "Recovery code used",
};

/** The audit actions the platform records, as sentences; an action this console does not know is shown verbatim. */
export const describeAction = (action: string): string => LABELS[action] ?? action;
export const KNOWN_ACTIONS: readonly string[] = Object.keys(LABELS);

export interface AuditFilter {
  action: string;
  /** An organization id, or empty for every event. */
  company: string;
  /** Inclusive UTC days (`YYYY-MM-DD`), or empty. */
  from: string;
  to: string;
}

/** The server pages by id only, so the filters apply to the entries already loaded. */
export function filterEntries(entries: readonly AuditEntry[], { action, company, from, to }: AuditFilter): AuditEntry[] {
  return entries.filter((entry) => {
    const day = entry.recorded_at.slice(0, 10);
    return (!action || entry.action === action) && (!company || entry.organization_id === company) && (!from || day >= from) && (!to || day <= to);
  });
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const age = now.getTime() - then;
  if (age < MINUTE) return "just now";
  if (age < HOUR) return `${Math.floor(age / MINUTE)} minutes ago`;
  if (age < DAY) return `${Math.floor(age / HOUR)} hours ago`;
  if (age < 2 * DAY) return "yesterday";
  if (age < 7 * DAY) return `${Math.floor(age / DAY)} days ago`;
  return formatDate(iso);
}