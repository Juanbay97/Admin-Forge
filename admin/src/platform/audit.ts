import type { AuditEntry } from "../api/platform";
import { t } from "../i18n/config";
import { formatDate } from "../lib/format";

/** The audit actions the platform records (the catalogue key is the action with its dot written as an underscore). */
export const KNOWN_ACTIONS = [
  "company.created",
  "company.suspended",
  "company.reactivated",
  "company.branding_saved",
  "company.gateway_assigned",
  "company.model_access_set",
  "gateway_key.created",
  "gateway_key.rotated",
  "gateway_key.status_changed",
  "company.models_discovered",
  "company.catalog_published",
  "model_price.set",
  "owner.mfa_enrolled",
  "owner.mfa_recovery_used",
] as const;

type KnownAction = (typeof KNOWN_ACTIONS)[number];
const isKnown = (action: string): action is KnownAction => (KNOWN_ACTIONS as readonly string[]).includes(action);

/** The audit actions as sentences in the active language; an action this console does not know is shown verbatim. */
export const describeAction = (action: string): string => (isKnown(action) ? t(`platform:audit.actions.${action.replace(".", "_") as ActionKey}`) : action);

type ActionKey = KnownAction extends infer A ? (A extends `${infer Head}.${infer Tail}` ? `${Head}_${Tail}` : never) : never;

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
  if (age < MINUTE) return t("time.justNow");
  if (age < HOUR) return t("time.minutesAgo", { count: Math.floor(age / MINUTE) });
  if (age < DAY) return t("time.hoursAgo", { count: Math.floor(age / HOUR) });
  if (age < 2 * DAY) return t("time.yesterday");
  if (age < 7 * DAY) return t("time.daysAgo", { count: Math.floor(age / DAY) });
  return formatDate(iso);
}