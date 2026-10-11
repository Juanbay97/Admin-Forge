import { ApiError } from "../api/client";
import type { Gateway, GatewayStatus } from "../api/gateway";

/** The key is write-only, so a saved gateway is reported as configured and nothing more. */
export const gatewayStateLabel = (status: GatewayStatus) =>
  status === "NOT_CONFIGURED" ? "Not configured" : "Configured";

/** The recorded endpoint is preselected only while the deployment still allow-lists it. */
export const chooseEndpoint = (gateway: Gateway) =>
  gateway.allowed_endpoints.includes(gateway.endpoint) ? gateway.endpoint : (gateway.allowed_endpoints[0] ?? "");

/** Server detail is never shown: messages are fixed, redacted and say what to do next. */
export function describeGatewayFailure(failure: unknown, action: "load" | "save"): string {
  if (failure instanceof ApiError && failure.code === "REVISION_CONFLICT") {
    return "The gateway configuration was changed by someone else. Reload to see the latest version; nothing was overwritten.";
  }
  if (action === "save" && failure instanceof ApiError && failure.status === 422) {
    return "The base URL or key was not accepted. Check them and try again.";
  }
  return action === "load" ? "The gateway settings could not be loaded. Try again." : "The key could not be saved. Try again.";
}