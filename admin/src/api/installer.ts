import { z } from "../lib/zod";
import { stampedFilename } from "../portal/download";
import { ApiError, type ApiClient, type DownloadClient } from "./client";

// `GET /forge/v1/capabilities/installer-config`: the per-company file the desktop installer reads (company code, control plane origin
// and the public policy keys to pin). Strict on purpose: it is saved to disk and handed to another program.
const Key = z.strictObject({
  kid: z.string().regex(/^[a-f0-9]{16}$/),
  alg: z.literal("Ed25519"),
  public_key: z.string().regex(/^[A-Za-z0-9_-]{43}$/),
  status: z.enum(["active", "retired"]),
});
const InstallerConfig = z.strictObject({
  schema: z.literal("forge.installer-config.v1"),
  company_code: z.string().regex(/^[a-z0-9][a-z0-9-]{0,62}$/),
  control_plane_origin: z.string().regex(/^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/),
  policy_keys: z.strictObject({ schema: z.literal("forge.capability-keys.v1"), keys: z.array(Key).min(1).max(9) }),
});

export type InstallerConfig = z.infer<typeof InstallerConfig>;

export const parseInstallerConfig = (raw: unknown): InstallerConfig | null => {
  const parsed = InstallerConfig.safeParse(raw);
  return parsed.success ? parsed.data : null;
};

export interface InstallerApi {
  /** The configuration of one company the signed-in member belongs to. */
  config(orgId: string): Promise<InstallerConfig>;
  /** The published installer, stamped with the company code in its file name (`GET /forge/v1/downloads/company`). */
  stamped(orgId: string, code: string | null): Promise<{ blob: Blob; filename: string }>;
}

export function createInstallerApi(client: ApiClient, downloads?: DownloadClient): InstallerApi {
  return {
    async stamped(orgId, code) {
      if (!downloads) throw new ApiError(0, "UNAVAILABLE", "Downloads are not available in this session.");
      const file = await downloads.download(`/forge/v1/downloads/company?org=${encodeURIComponent(orgId)}`);
      return { blob: file.blob, filename: stampedFilename(file.disposition, code) };
    },
    async config(orgId) {
      const parsed = parseInstallerConfig(await client.request("GET", `/forge/v1/capabilities/installer-config?org=${encodeURIComponent(orgId)}`));
      if (!parsed) throw new ApiError(200, "INVALID_RESPONSE", "The server sent the configuration in an unexpected shape.");
      return parsed;
    },
  };
}