import { ApiError } from "../api/client";
import { t } from "../i18n/config";

/** The API error codes that have their own copy (the `errors` group of the common catalogue). */
export const ERROR_CODES = [
  "UNAUTHENTICATED", "MFA_REQUIRED", "MFA_INVALID", "MFA_LOCKED", "MFA_ENROLLED", "PLATFORM_DENIED", "COMPANY_CONFLICT", "NO_ACTIVE_MEMBER",
  "KEY_CONFLICT", "INVALID_RESPONSE", "FORBIDDEN", "NOT_FOUND", "REVISION_CONFLICT", "LAST_ADMIN", "INVALID_REQUEST", "RATE_LIMITED",
  "SERVICE_UNAVAILABLE", "NETWORK",
] as const;
type ErrorCode = (typeof ERROR_CODES)[number];

const known = (code: string): code is ErrorCode => (ERROR_CODES as readonly string[]).includes(code);

/** One copy table for every area, in the active language: the API error code decides the message, never the server's free text. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError && known(error.code) ? t(`errors.${error.code}`) : t("errors.generic");
}

/** Sign-in or a session step that must be completed with a second factor. */
export function needsMfa(error: unknown): boolean {
  return error instanceof ApiError && error.code === "MFA_REQUIRED";
}
