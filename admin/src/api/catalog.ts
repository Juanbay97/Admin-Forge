import type { ApiClient } from "./client";

export type PublicationState = "CURRENT" | "UNPUBLISHED" | "STALE_GATEWAY";

export interface CatalogStatus {
  catalogue_revision: number;
  default_model: string | null;
  publication_state: PublicationState;
}

export interface Discovery {
  gateway_revision: number;
  model_ids: string[];
}

export interface PublishInput {
  aliases: Record<string, string>;
  defaultAlias: string;
  expectedCatalogueRevision: number;
  expectedGatewayRevision: number;
  operationId: string;
}

export interface CatalogApi {
  status(orgId: string): Promise<CatalogStatus>;
  refresh(orgId: string): Promise<Discovery>;
  publish(orgId: string, input: PublishInput): Promise<void>;
  /** What a member sees: the published aliases, exactly. */
  published(orgId: string): Promise<{ defaultModel: string; aliases: string[] }>;
}

export function createCatalogApi(client: ApiClient): CatalogApi {
  const org = (orgId: string) => `/forge/v1/orgs/${encodeURIComponent(orgId)}`;
  return {
    status: (orgId) => client.request<CatalogStatus>("GET", `${org(orgId)}/gateway/catalogue/status`),
    refresh: (orgId) => client.request<Discovery>("POST", `${org(orgId)}/gateway/catalogue/refresh`),
    async publish(orgId, input) {
      await client.request("POST", `${org(orgId)}/models/publish`, {
        operation_id: input.operationId,
        expected_catalogue_revision: input.expectedCatalogueRevision,
        expected_gateway_revision: input.expectedGatewayRevision,
        aliases: input.aliases,
        default_alias: input.defaultAlias,
      });
    },
    async published(orgId) {
      const body = await client.request<{ default_model: string; models: Array<{ id: string }> }>("GET", `${org(orgId)}/models`);
      return { defaultModel: body.default_model, aliases: body.models.map((model) => model.id) };
    },
  };
}