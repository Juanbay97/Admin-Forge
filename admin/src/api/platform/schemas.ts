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
export const CompanyUsage = z.strictObject({ organization_id: Uuid, slug: z.string(), display_name: z.string(), ...Counters });
export const CompanyUsageList = z.strictObject({ companies: z.array(CompanyUsage), next_after: z.string().nullable() });
export const ModelUsage = z.strictObject({ upstream_id: z.string(), ...Counters });
export const ModelUsageList = z.strictObject({ models: z.array(ModelUsage), next_after: z.string().nullable() });

export type PlatformMe = z.infer<typeof PlatformMe>;
export type Enrollment = z.infer<typeof Enrollment>;
export type Company = z.infer<typeof Company>;
export type CompanyList = z.infer<typeof CompanyList>;
export type CreatedCompany = z.infer<typeof CreatedCompany>;
export type AuditEntry = z.infer<typeof AuditEntry>;
export type AuditPage = z.infer<typeof AuditPage>;
export type GatewayKey = z.infer<typeof GatewayKey>;
export type GatewayKeyList = z.infer<typeof GatewayKeyList>;
export type KeyAssignment = z.infer<typeof KeyAssignment>;
export type Price = z.infer<typeof Price>;
export type UsageTotals = z.infer<typeof UsageTotals>;
export type CompanyUsage = z.infer<typeof CompanyUsage>;
export type ModelUsage = z.infer<typeof ModelUsage>;