import type { GatewayStatus } from "../api/gateway";

/** The key is the platform's, so a gateway is reported as configured and nothing more. */
export const gatewayStateLabel = (status: GatewayStatus) =>
  status === "NOT_CONFIGURED" ? "Not configured" : "Configured";

/** Server detail is never shown: the message is fixed, redacted and says what to do next. */
export const describeGatewayFailure = (_failure: unknown) => "The gateway settings could not be loaded. Try again.";
