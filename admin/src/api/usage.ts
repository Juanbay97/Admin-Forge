import { z } from "../lib/zod";
import { ApiError, type ApiClient } from "./client";

const Counters = {
  requests: z.number().int(),
  prompt_tokens: z.number().int(),
  completion_tokens: z.number().int(),
  estimated_requests: z.number().int(),
  error_requests: z.number().int(),
  cost_micros: z.number().int(),
  unpriced_requests: z.number().int(),
};

/** `GET /forge/v1/orgs/{id}/usage/me`: the member's own counters. Cost is shown only when the server reports it. */
const MyUsage = z.strictObject(Counters);
/** `GET /forge/v1/orgs/{id}/usage/members` (organization administrators): one row per person. */
const MemberRow = z.strictObject({ member_id: z.string().uuid(), email: z.string(), name: z.string(), state: z.string(), ...Counters });
const MemberPage = z.strictObject({ members: z.array(MemberRow), next_after: z.string().nullable() });

export type MyUsage = z.infer<typeof MyUsage>;
export type MemberUsage = z.infer<typeof MemberRow>;
export interface Window {
  from: string;
  to: string;
}

const invalid = (): never => {
  throw new ApiError(200, "INVALID_RESPONSE", "The server sent usage in an unexpected shape.");
};

export function parseMemberRows(raw: unknown): { members: MemberUsage[]; next_after: string | null } {
  const parsed = MemberPage.safeParse(raw);
  return parsed.success ? parsed.data : invalid();
}

export interface UsageApi {
  /** `null` when this server has no per-member usage route (404): the page says it is not available yet. */
  mine(orgId: string, window: Window): Promise<MyUsage | null>;
  members(orgId: string, window: Window & { after?: string }): Promise<{ members: MemberUsage[]; next_after: string | null }>;
  /** Every person, following the cursor (at most 100 per page, a safety stop at 2,000 people). */
  allMembers(orgId: string, window: Window): Promise<MemberUsage[]>;
}

const PAGE = 100;

export function createUsageApi(client: ApiClient): UsageApi {
  const base = (orgId: string) => `/forge/v1/orgs/${encodeURIComponent(orgId)}/usage`;
  const members: UsageApi["members"] = async (orgId, { from, to, after }) =>
    parseMemberRows(await client.request("GET", `${base(orgId)}/members?from=${from}&to=${to}${after ? `&after=${encodeURIComponent(after)}` : ""}&page=${PAGE}`));
  return {
    async mine(orgId, { from, to }) {
      try {
        const parsed = MyUsage.safeParse(await client.request("GET", `${base(orgId)}/me?from=${from}&to=${to}`));
        return parsed.success ? parsed.data : invalid();
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    members,
    async allMembers(orgId, window) {
      const all: MemberUsage[] = [];
      let after: string | undefined;
      for (let index = 0; index < 20; index += 1) {
        const page = await members(orgId, { ...window, after });
        all.push(...page.members);
        if (!page.next_after) break;
        after = page.next_after;
      }
      return all;
    },
  };
}