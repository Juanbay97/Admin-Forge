import type { ApiClient } from "./client";

export type GatewayStatus = "NOT_CONFIGURED" | "SAVED_UNVERIFIED";

export interface GatewaySaved {
  status: GatewayStatus;
  revision: number;
  endpoint: string;
}

export interface Gateway extends GatewaySaved {
  allowed_endpoints: string[];
}

export interface SaveKeyInput {
  endpoint: string;
  apiKey: string;
  expectedRevision: number;
}

export interface GatewayApi {
  get(orgId: string): Promise<Gateway>;
  save(orgId: string, input: SaveKeyInput): Promise<GatewaySaved>;
}

export function createGatewayApi(client: ApiClient): GatewayApi {
  const path = (orgId: string) => `/forge/v1/orgs/${encodeURIComponent(orgId)}/gateway`;
  return {
    get: (orgId) => client.request<Gateway>("GET", path(orgId)),
    save: (orgId, { endpoint, apiKey, expectedRevision }) =>
      client.request<GatewaySaved>("PUT", path(orgId), {
        expected_revision: expectedRevision,
        api_key: apiKey,
        endpoint,
      }),
  };
}