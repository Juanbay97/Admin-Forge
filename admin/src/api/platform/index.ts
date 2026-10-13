import { z } from "../../lib/zod";
import { parseBranding, type Branding } from "../../brand/branding";
import type { BrandingDocument } from "../branding";
import { ApiError, type ApiClient } from "../client";
import * as S from "./schemas";

export type { AuditEntry, AuditPage, Company, CompanyList, CompanyMember, CompanyMemberPage, CompanyUsage, CreatedCompany, Enrollment, GatewayKey, GatewayKeyList, KeyAssignment, ModelUsage, Overview, PlatformMe, Price, UsageDay, UsageTotals } from "./schemas";

export interface NewCompany {
  slug: string;
  display_name: string;
  department: string;
  admin_email: string;
  admin_name: string;
}
export interface AssignmentEntry {
  key_id: string;
  priority: number;
  active: boolean;
}
export interface Window {
  from: string;
  to: string;
  after?: string;
}

/** The hidden platform API (`/forge/v1/platform/*`), parsed at the boundary. The 15-minute lock and the 30-minute freshness live on the server. */
export interface PlatformApi {
  me(): Promise<S.PlatformMe>;
  enroll(): Promise<S.Enrollment>;
  verify(factor: { code: string } | { recovery_code: string }): Promise<void>;
  companies(page: { after?: string; page?: number }): Promise<S.CompanyList>;
  company(id: string): Promise<S.Company>;
  /** The people of one company (read-only, the directory shape), by membership id cursor. */
  companyMembers(id: string, page: { after?: string; page?: number }): Promise<S.CompanyMemberPage>;
  createCompany(company: NewCompany): Promise<S.CreatedCompany>;
  suspend(id: string): Promise<S.Company>;
  reactivate(id: string): Promise<S.Company>;
  branding(id: string): Promise<Branding>;
  saveBranding(id: string, expectedRevision: number, document: BrandingDocument): Promise<Branding>;
  resetBranding(id: string, expectedRevision: number): Promise<Branding>;
  audit(page: { before?: number; page?: number }): Promise<S.AuditPage>;
  keys(): Promise<S.GatewayKeyList>;
  createKey(key: { label: string; origin: string; key?: string }): Promise<S.GatewayKey>;
  rotateKey(id: string, expectedRevision: number, key: string): Promise<S.GatewayKey>;
  setKeyEnabled(id: string, enabled: boolean): Promise<S.GatewayKey>;
  companyKeys(id: string): Promise<{ keys: S.KeyAssignment[] }>;
  assignKeys(id: string, entries: AssignmentEntry[]): Promise<{ keys: S.KeyAssignment[] }>;
  modelAccess(id: string): Promise<{ models: string[] }>;
  setModelAccess(id: string, models: string[]): Promise<{ models: string[] }>;
  prices(upstreamId?: string): Promise<{ prices: S.Price[] }>;
  setPrice(price: { upstream_id: string; input_micros: number; output_micros: number; effective_from?: string }): Promise<S.Price>;
  usageTotals(window: Window): Promise<S.UsageTotals>;
  /** Companies, active people, totals and the previous period in one read. */
  overview(window: Window): Promise<S.Overview>;
  /** Every UTC day of the window in order (zeros included) with the people active that day. */
  usageDays(window: Window): Promise<z.infer<typeof S.UsageDays>>;
  usageByCompany(window: Window): Promise<z.infer<typeof S.CompanyUsageList>>;
  usageByModel(window: Window): Promise<z.infer<typeof S.ModelUsageList>>;
}

const BASE = "/forge/v1/platform";

function parse<T>(schema: z.ZodType<T>, raw: unknown): T {
  const result = schema.safeParse(raw);
  if (!result.success) throw new ApiError(200, "INVALID_RESPONSE", `The server sent an unexpected shape at ${result.error.issues[0]?.path.join(".") || "(root)"}.`);
  return result.data;
}

const query = (values: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined) search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : "";
};

export function createPlatformApi(client: ApiClient): PlatformApi {
  const get = async <T>(schema: z.ZodType<T>, path: string) => parse(schema, await client.request("GET", BASE + path));
  const send = async <T>(method: string, schema: z.ZodType<T>, path: string, body?: unknown) => parse(schema, await client.request(method, BASE + path, body));
  const company = (id: string) => `/companies/${encodeURIComponent(id)}`;
  const brand = (raw: unknown): Branding => {
    try {
      return parseBranding(raw);
    } catch {
      throw new ApiError(200, "INVALID_RESPONSE", "The server sent branding in an unexpected shape.");
    }
  };
  return {
    me: () => get(S.PlatformMe, "/me"),
    enroll: () => send("POST", S.Enrollment, "/mfa/enroll", {}),
    async verify(factor) {
      await client.request("POST", `${BASE}/login/mfa`, factor);
    },
    companies: ({ after, page }) => get(S.CompanyList, `/companies${query({ after, page })}`),
    company: (id) => get(S.Company, company(id)),
    companyMembers: (id, { after, page }) => get(S.CompanyMemberPage, `${company(id)}/members${query({ after, page })}`),
    createCompany: (value) => send("POST", S.CreatedCompany, "/companies", value),
    suspend: (id) => send("POST", S.Company, `${company(id)}/suspend`, {}),
    reactivate: (id) => send("POST", S.Company, `${company(id)}/reactivate`, {}),
    branding: async (id) => brand(await client.request("GET", `${BASE}${company(id)}/branding`)),
    saveBranding: async (id, expectedRevision, document) => brand(await client.request("PUT", `${BASE}${company(id)}/branding`, { expectedRevision, branding: document })),
    resetBranding: async (id, expectedRevision) => brand(await client.request("POST", `${BASE}${company(id)}/branding/reset`, { expectedRevision })),
    audit: ({ before, page }) => get(S.AuditPage, `/audit${query({ before, page })}`),
    keys: () => get(S.GatewayKeyList, "/gateway-keys"),
    createKey: (value) => send("POST", S.GatewayKey, "/gateway-keys", value),
    rotateKey: (id, expectedRevision, key) => send("POST", S.GatewayKey, `/gateway-keys/${encodeURIComponent(id)}/rotate`, { expected_revision: expectedRevision, key }),
    setKeyEnabled: (id, enabled) => send("POST", S.GatewayKey, `/gateway-keys/${encodeURIComponent(id)}/${enabled ? "enable" : "disable"}`, {}),
    companyKeys: (id) => get(S.KeyAssignments, `${company(id)}/gateway-keys`),
    assignKeys: (id, keys) => send("PUT", S.KeyAssignments, `${company(id)}/gateway-keys`, { keys }),
    modelAccess: (id) => get(S.ModelAccess, `${company(id)}/model-access`),
    setModelAccess: (id, models) => send("PUT", S.ModelAccess, `${company(id)}/model-access`, { models }),
    prices: (upstreamId) => get(S.PriceList, `/prices${query({ upstream_id: upstreamId })}`),
    setPrice: (price) => send("POST", S.Price, "/prices", price),
    usageTotals: ({ from, to }) => get(S.UsageTotals, `/usage/totals${query({ from, to })}`),
    overview: ({ from, to }) => get(S.Overview, `/overview${query({ from, to })}`),
    usageDays: ({ from, to }) => get(S.UsageDays, `/usage/days${query({ from, to })}`),
    usageByCompany: ({ from, to, after }) => get(S.CompanyUsageList, `/usage/companies${query({ from, to, after })}`),
    usageByModel: ({ from, to, after }) => get(S.ModelUsageList, `/usage/models${query({ from, to, after })}`),
  };
}