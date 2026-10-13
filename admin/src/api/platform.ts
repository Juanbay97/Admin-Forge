import { z } from "../lib/zod";
import type { ApiClient } from "./client";

const PlatformMe = z.object({
  role: z.enum(["platform_owner", "platform_viewer"]),
  mfa: z.enum(["none", "totp"]),
});

export type PlatformMe = z.infer<typeof PlatformMe>;

/** The platform role of the signed-in account (change fv2-platform-core). 403/404 mean "not a platform account". */
export interface PlatformApi {
  me(): Promise<PlatformMe>;
}

export function createPlatformApi(client: ApiClient): PlatformApi {
  return { me: async () => PlatformMe.parse(await client.request("GET", "/forge/v1/platform/me")) };
}