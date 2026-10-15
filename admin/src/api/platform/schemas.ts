import { z } from "../../lib/zod";

// Response shapes of the hidden platform routes (src/forge/platform_*_api.py). Objects are strict: a field the server adds or
// renames fails here, at the boundary, instead of rendering `undefined` three components away.
const Uuid = z.string().uuid();
const Instant = z.string().min(1);

export const PlatformMe = z.strictObject({
  account_id: z.string().min(1),
  role: z.enum(["platform_owner"]),
  mfa: z.strictObject({ state: z.enum(["none", "pending", "active"]), verified: z.boolean(), fresh: z.boolean() }),
});

export const Enrollment = z.strictObject({ secret: z.string().min(16), otpauth_uri: z.string().startsWith("otpauth://totp/"), recovery_codes: z.array(z.string().min(1)).min(1) });

export const Company = z.strictObject({ id: Uuid, slug: z.string().min(1), display_name: z.string().min(1), active: z.boolean() });
export const CompanyList = z.strictObject({ companies: z.array(Company), next_after: z.string().nullable() });
export const CreatedCompany = Company.extend({
  invitation: z.strictObject({ id: Uuid, expires_at: Instant, delivery_state: z.string().min(1), delivery_channel: z.string().min(1) }),
});

export const CompanyMember = z.strictObject({
  id: Uuid,
  email: z.string().min(1),
  display_name: z.string(),
  status: z.enum(["active", "suspended"]),
  roles: z.array(z.string()),
  departments: z.array(z.strictObject({ id: Uuid, name: z.string() })),
});
export const CompanyMemberPage = z.strictObject({ members: z.array(CompanyMember), next_after: z.string().nullable() });

export const AuditEntry = z.strictObject({ id: z.number().int(), actor_id: Uuid, action: z.string().min(1), organization_id: Uuid.nullable(), recorded_at: Instant });
export const AuditPage = z.strictObject({ entries: z.array(AuditEntry), next_before: z.number().int().nullable() });

export const GatewayKey = z.strictObject({
  id: Uuid,
  label: z.string().min(1),
  origin: z.string().min(1),
  revision: z.number().int(),
  status: z.string().min(1),
  has_key: z.boolean(),
  hint: z.string().nullable(),
  companies: z.number().int(),
});
export const GatewayKeyList = z.strictObject({ keys: z.array(GatewayKey), allowed_origins: z.array(z.string()) });

export const KeyAssignment = z.strictObject({
  key_id: Uuid,
  label: z.string(),
  origin: z.string(),
  priority: z.number().int(),
  active: z.boolean(),
  key_status: z.string(),
  has_key: z.boolean(),
});
export const KeyAssignments = z.strictObject({ keys: z.array(KeyAssignment) });
export const ModelAccess = z.strictObject({ models: z.array(z.string()) });

export const KEY_DISCOVERY_STATES = ["ok", "inactive", "disabled", "no_key", "unreadable", "unreachable"] as const;
const CatalogState = z.enum(["UNPUBLISHED", "CURRENT", "STALE_GATEWAY"]);
/** `GET companies/{id}/catalog`: nothing to show until a gateway key is assigned, then the stored discovery and the published selection. */
export const CatalogRead = z.union([
  z.strictObject({ configured: z.literal(false) }),
  z.strictObject({
    configured: z.literal(true),
    gateway_revision: z.number().int(),
    ceiling: z.array(z.string()).nullable(),
    discovered: z.strictObject({ model_ids: z.array(z.string()), at: Instant }).nullable(),
    catalogue: z.strictObject({ revision: z.number().int(), default_model: z.string().nullable(), state: CatalogState, aliases: z.record(z.string(), z.string()) }),
  }),
]);
/** `POST companies/{id}/catalog/discover`: one finite state per assigned key, and the union that was stored. */
export const CatalogDiscovery = z.strictObject({
  keys: z.array(z.strictObject({ key_id: Uuid, label: z.string(), origin: z.string(), priority: z.number().int(), state: z.enum(KEY_DISCOVERY_STATES), model_count: z.number().int(), model_ids: z.array(z.string()) })),
  model_ids: z.array(z.string()),
  discovered_at: Instant.nullable(),
});
export const CatalogPublished = z.strictObject({ revision: z.number().int(), default_model: z.string(), models: z.array(z.string()) });

export const Price = z.strictObject({
  id: z.number().int(),
  upstream_id: z.string().min(1),
  version: z.number().int(),
  input_micros: z.number().int(),
  output_micros: z.number().int(),
  currency: z.string(),
  effective_from: Instant,
  set_by: Uuid,
});
export const PriceList = z.strictObject({ prices: z.array(Price) });

const Counters = {
  requests: z.number().int(),
  prompt_tokens: z.number().int(),
  completion_tokens: z.number().int(),
  estimated_requests: z.number().int(),
  error_requests: z.number().int(),
  cost_micros: z.number().int(),
  unpriced_requests: z.number().int(),
};
export const UsageTotals = z.strictObject({ companies: z.number().int(), ...Counters });
/** `GET /overview`: companies, active people, the range's counters and the previous period's figures in one read. */
export const Overview = z.strictObject({
  companies: z.strictObject({ active: z.number().int(), suspended: z.number().int() }),
  active_users: z.number().int(),
  ...Counters,
  previous: z.strictObject({ active_users: z.number().int(), requests: z.number().int(), prompt_tokens: z.number().int(), completion_tokens: z.number().int(), cost_micros: z.number().int() }),
});
/** `GET /usage/days`: one row per UTC day of the range, zeros included. */
export const UsageDay = z.strictObject({ day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), ...Counters, active_users: z.number().int() });
export const UsageDays = z.strictObject({ days: z.array(UsageDay) });
export const CompanyUsage = z.strictObject({ organization_id: Uuid, slug: z.string(), display_name: z.string(), ...Counters });
export const CompanyUsageList = z.strictObject({ companies: z.array(CompanyUsage), next_after: z.string().nullable() });
export const ModelUsage = z.strictObject({ upstream_id: z.string(), ...Counters });
export const ModelUsageList = z.strictObject({ models: z.array(ModelUsage), next_after: z.string().nullable() });

export type PlatformMe = z.infer<typeof PlatformMe>;
export type Enrollment = z.infer<typeof Enrollment>;
export type Company = z.infer<typeof Company>;
export type CompanyList = z.infer<typeof CompanyList>;
export type CreatedCompany = z.infer<typeof CreatedCompany>;
export type CompanyMember = z.infer<typeof CompanyMember>;
export type CompanyMemberPage = z.infer<typeof CompanyMemberPage>;
export type AuditEntry = z.infer<typeof AuditEntry>;
export type AuditPage = z.infer<typeof AuditPage>;
export type GatewayKey = z.infer<typeof GatewayKey>;
export type GatewayKeyList = z.infer<typeof GatewayKeyList>;
export type KeyAssignment = z.infer<typeof KeyAssignment>;
export type CatalogRead = z.infer<typeof CatalogRead>;
export type CatalogDiscovery = z.infer<typeof CatalogDiscovery>;
export type CatalogPublished = z.infer<typeof CatalogPublished>;
export type KeyDiscoveryState = (typeof KEY_DISCOVERY_STATES)[number];
export type Price = z.infer<typeof Price>;
export type UsageTotals = z.infer<typeof UsageTotals>;
export type Overview = z.infer<typeof Overview>;
export type UsageDay = z.infer<typeof UsageDay>;
export type CompanyUsage = z.infer<typeof CompanyUsage>;
export type ModelUsage = z.infer<typeof ModelUsage>;