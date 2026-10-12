import { ApiError, type UploadClient } from "./client";
import { BrandingParseError, parseBranding, type AssetKind, type Branding, type draftToDocument } from "../brand/branding";

export type BrandingDocument = ReturnType<typeof draftToDocument>;

export interface UploadedAsset {
  sha256: string;
  width: number;
  height: number;
}

export interface BrandingApi {
  get(orgId: string): Promise<Branding>;
  save(orgId: string, expectedRevision: number, document: BrandingDocument): Promise<Branding>;
  reset(orgId: string, expectedRevision: number): Promise<Branding>;
  uploadAsset(orgId: string, kind: AssetKind, file: Blob): Promise<UploadedAsset>;
}

const SHA256 = /^[0-9a-f]{64}$/;

function invalid(): never {
  throw new ApiError(200, "INVALID_RESPONSE", "The server sent branding in an unexpected shape.");
}

function checked(raw: unknown): Branding {
  try {
    return parseBranding(raw);
  } catch (error) {
    if (error instanceof BrandingParseError) invalid();
    throw error;
  }
}

function uploaded(raw: unknown): UploadedAsset {
  const body = raw as { sha256?: unknown; width?: unknown; height?: unknown } | null;
  if (
    typeof body?.sha256 !== "string" ||
    !SHA256.test(body.sha256) ||
    !Number.isInteger(body.width) ||
    !Number.isInteger(body.height)
  ) {
    invalid();
  }
  return { sha256: body.sha256, width: body.width as number, height: body.height as number };
}

export function createBrandingApi(client: UploadClient): BrandingApi {
  const path = (orgId: string) => `/forge/v1/orgs/${encodeURIComponent(orgId)}/branding`;
  return {
    get: async (orgId) => checked(await client.request("GET", path(orgId))),
    save: async (orgId, expectedRevision, document) =>
      checked(await client.request("PUT", path(orgId), { expectedRevision, branding: document })),
    reset: async (orgId, expectedRevision) =>
      checked(await client.request("POST", `${path(orgId)}/reset`, { expectedRevision })),
    uploadAsset: async (orgId, kind, file) =>
      uploaded(await client.upload(`${path(orgId)}/assets?kind=${kind}`, file, file.type || "application/octet-stream")),
  };
}
