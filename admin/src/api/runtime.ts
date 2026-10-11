import { session } from "../auth/session";
import { createAccountApi } from "./account";
import { createApiClient } from "./client";

export const accountApi = createAccountApi(createApiClient({ session }));