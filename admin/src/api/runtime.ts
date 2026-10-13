import { session } from "../auth/session";
import { createAccountApi } from "./account";
import { createBrandingApi } from "./branding";
import { createCatalogApi } from "./catalog";
import { createApiClient } from "./client";
import { createDownloadsApi } from "./downloads";
import { createGatewayApi } from "./gateway";
import { createUsageApi } from "./usage";
import { createInvitationsApi } from "./invitations";
import { createMembersApi } from "./members";
import { createPlatformApi } from "./platform";
import type { Services } from "./services";

const client = createApiClient({ session });
export const services: Services = {
  account: createAccountApi(client),
  members: createMembersApi(client),
  gateway: createGatewayApi(client),
  catalog: createCatalogApi(client),
  branding: createBrandingApi(client),
  platform: createPlatformApi(client),
  invitations: createInvitationsApi(client),
  downloads: createDownloadsApi(),
  usage: createUsageApi(client),
};