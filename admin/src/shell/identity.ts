import type { AccountApi, Me, Organization } from "../api/account";
import { ApiError } from "../api/client";
import type { PlatformApi, PlatformMe } from "../api/platform";
import type { AreaId } from "./areas";

export interface Identity {
  account: Me["account"];
  platform: Pick<PlatformMe, "role" | "mfa"> | null;
  orgs: Organization[];
}

/** platform role -> /platform; an organization administrator -> /company; everyone else -> /portal. */
export function homeFor(identity: Identity): AreaId {
  if (identity.platform) return "platform";
  if (identity.orgs.some((organization) => organization.roles.includes("organization_admin"))) return "company";
  return "portal";
}

/**
 * The account plus its platform role. 403 and 404 from platform/me mean "not a platform account" (never an error); any other
 * failure is one. While no platform area exists (`probePlatform: false`) the probe is not made at all.
 */
export async function loadIdentity(
  api: { account: AccountApi; platform?: Pick<PlatformApi, "me"> },
  { probePlatform = true }: { probePlatform?: boolean } = {},
): Promise<Identity> {
  const [me, platform] = await Promise.all([
    api.account.me(),
    probePlatform && api.platform ? api.platform.me().catch((error: unknown) => {
      if (error instanceof ApiError && (error.status === 403 || error.status === 404)) return null;
      throw error;
    }) : Promise.resolve(null),
  ]);
  return {
    account: me.account,
    orgs: me.organizations,
    platform: platform ? { role: platform.role, mfa: platform.mfa } : null,
  };
}