import type { AccountApi } from "./account";
import type { BrandingApi } from "./branding";
import type { CatalogApi } from "./catalog";
import type { GatewayApi } from "./gateway";
import type { InvitationsApi } from "./invitations";
import type { MembersApi } from "./members";
import type { PlatformApi } from "./platform";

/** Everything a screen may call; the console hands each page only the port it needs. */
export interface Services {
  account: AccountApi;
  members: MembersApi;
  gateway: GatewayApi;
  catalog: CatalogApi;
  branding: BrandingApi;
  platform: PlatformApi;
  invitations: InvitationsApi;
}