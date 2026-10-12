import { session } from "../auth/session";
import { createAccountApi } from "./account";
import { createBrandingApi } from "./branding";
import { createCatalogApi } from "./catalog";
import { createApiClient } from "./client";
import { createGatewayApi } from "./gateway";
import { createMembersApi } from "./members";
import type { Services } from "./services";

const client = createApiClient({ session });
export const services: Services = {
  account: createAccountApi(client),
  members: createMembersApi(client),
  gateway: createGatewayApi(client),
  catalog: createCatalogApi(client),
  branding: createBrandingApi(client),
};