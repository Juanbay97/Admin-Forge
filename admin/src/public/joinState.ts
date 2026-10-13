import { ApiError } from "../api/client";

/** What the page says when accepting fails. The server never says why an invitation is unusable (expired, used, wrong): one 404. */
export type JoinFailure = "invalid" | "existing_account" | "password" | "throttled" | "unavailable" | "offline";

export function joinStateFor(error: unknown): JoinFailure {
  if (!(error instanceof ApiError)) return "unavailable";
  if (error.status === 0) return "offline";
  if (error.status === 404) return "invalid";
  if (error.status === 409 && error.code === "EXISTING_ACCOUNT_AUTH_REQUIRED") return "existing_account";
  if (error.status === 422) return "password";
  if (error.status === 429) return "throttled";
  return "unavailable";
}