import type { Services } from "../api/services";
import { session } from "../auth/session";

/** Set while the user is signing out, so the shell can tell that from a session that expired under them. */
export const exit = { intentional: false };

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