import type { ApiClient } from "./client";

export type GatewayStatus = "NOT_CONFIGURED" | "SAVED_UNVERIFIED";

/** Read-only status. ``revision`` is the number of usable platform keys; no origin or key data is ever returned. */
export interface Gateway {
  status: GatewayStatus;
  revision: number;
  endpoint: string;
  allowed_endpoints: string[];
}

export interface GatewayApi {
  get(orgId: string): Promise<Gateway>;
}

export function createGatewayApi(client: ApiClient): GatewayApi {
  const path = (orgId: string) => `/forge/v1/orgs/${encodeURIComponent(orgId)}/gateway`;
  return {
    get: (orgId) => client.request<Gateway>("GET", path(orgId)),
  };
}
