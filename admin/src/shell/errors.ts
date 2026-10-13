import { ApiError } from "../api/client";

/** One copy table for every area: the API error code decides the message, never the server's free text. */
export const ERROR_MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: "Your session expired. Sign in again to continue.",
  MFA_REQUIRED: "Two-factor verification is required.",
  MFA_INVALID: "That code was not accepted. Check it and try again.",
  MFA_LOCKED: "Too many attempts. Try again in 15 minutes.",
  MFA_ENROLLED: "A second factor is already set up for this account.",
  PLATFORM_DENIED: "This account cannot use the platform console.",
  COMPANY_CONFLICT: "A company with this code already exists.",
  KEY_CONFLICT: "A gateway key with this label already exists.",
  INVALID_RESPONSE: "The server answered in a way this console does not understand. Contact support.",
  FORBIDDEN: "You do not have access to this.",
  NOT_FOUND: "That could not be found.",
  REVISION_CONFLICT: "This was changed elsewhere. Reload to see the latest version.",
  LAST_ADMIN: "The last administrator cannot be suspended.",
  INVALID_REQUEST: "Check the details and try again.",
  RATE_LIMITED: "Too many attempts. Try again later.",
  SERVICE_UNAVAILABLE: "The service is temporarily unavailable. Try again shortly.",
  NETWORK: "The server could not be reached.",
};

const GENERIC = "Something went wrong. Try again.";

export function errorMessage(error: unknown): string {
  return (error instanceof ApiError && ERROR_MESSAGES[error.code]) || GENERIC;
}

/** Sign-in or a session step that must be completed with a second factor. */
export function needsMfa(error: unknown): boolean {
  return error instanceof ApiError && error.code === "MFA_REQUIRED";
}