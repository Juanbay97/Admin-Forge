import type { Services } from "../api/services";
import { session } from "../auth/session";

/** Set while the user is signing out, so the shell can tell that from a session that expired under them. */
export const exit: { intentional: boolean; notice: string | null } = { intentional: false, notice: null };

/** The email typed at sign-in, kept in memory only: a platform owner has no profile to read it from. */
export const hint: { email: string | null } = { email: null };

export const IDLE_NOTICE = "Signed out for inactivity.";

/** Drops the session on the user's behalf (idle timeout): the sign-in page says why instead of calling it an expiry. */
export function signOutWithNotice(notice: string): void {
  exit.notice = notice;
  session.clear();
}

export async function signOut(services: Services): Promise<void> {
  exit.intentional = true;
  try {
    await services.account.logout();
  } catch {
    // The token is dropped locally either way; the server expires it on its own.
  } finally {
    session.clear();
  }
}