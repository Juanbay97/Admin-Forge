import { session } from "../auth/session";
import { createAccountApi } from "./account";
import { createApiClient } from "./client";
import { createMembersApi } from "./members";

const client = createApiClient({ session });
export const accountApi = createAccountApi(client);
export const membersApi = createMembersApi(client);