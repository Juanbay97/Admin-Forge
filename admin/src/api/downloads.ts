import { z } from "../lib/zod";

// `/downloads/latest.json` is a static file the edge (or the local control plane) serves next to the installer. The installer url
// must be a same-origin file directly under /downloads/, so a manifest can never point the download button somewhere else.
const SAME_ORIGIN_FILE = /^\/downloads\/[A-Za-z0-9][A-Za-z0-9._-]*$/;

const Installer = z.strictObject({ url: z.string().regex(SAME_ORIGIN_FILE), sha256: z.string().regex(/^[a-f0-9]{64}$/), size_bytes: z.number().int().nonnegative() });
const Manifest = z.looseObject({ version: z.string().min(1), released_at: z.string().min(1), platforms: z.looseObject({ windows: Installer.optional() }) });

export type Installer = z.infer<typeof Installer>;
export type InstallerManifest = z.infer<typeof Manifest>;

export const parseManifest = (raw: unknown): InstallerManifest | null => {
  const parsed = Manifest.safeParse(raw);
  return parsed.success ? parsed.data : null;
};

export interface DownloadsApi {
  /** The published manifest, or `null` when there is none yet (404) or it is not a valid manifest. Network failures throw. */
  latest(): Promise<InstallerManifest | null>;
}

export function createDownloadsApi(fetchImpl: typeof fetch = (...args) => fetch(...args)): DownloadsApi {
  return {
    async latest() {
      const response = await fetchImpl("/downloads/latest.json", { credentials: "omit", referrerPolicy: "no-referrer", cache: "no-cache" });
      if (!response.ok) return null;
      try {
        return parseManifest(await response.json());
      } catch {
        return null;
      }
    },
  };
}