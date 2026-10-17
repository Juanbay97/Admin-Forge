import type { GatewayStatus } from "../api/gateway";
import { t } from "../i18n/config";

/** The key is the platform's, so a gateway is reported as configured and nothing more. */
export const gatewayStateLabel = (status: GatewayStatus) =>
  status === "NOT_CONFIGURED" ? t("company:gateway.notConfigured") : t("company:gateway.configured");

/** Server detail is never shown: the message is fixed, redacted and says what to do next. */
export const describeGatewayFailure = (_failure: unknown) => t("company:gateway.failure");
