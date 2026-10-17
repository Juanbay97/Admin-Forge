import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { session } from "../auth/session";
import { Login } from "../pages/Login";
import { exit, hint } from "./session";
import { useServices } from "./services";

/**
 * No token: the sign-in form is rendered in place, so the URL stays untouched and signing in returns to the same path
 * (nothing is stored). A token that disappears without the user signing out shows the expiry notice.
 */
export function RequireSession({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const services = useServices();
  const token = useSyncExternalStore(session.subscribe, session.token);
  const previous = useRef(token);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    if (token) {
      setExpired(false);
      exit.notice = null;
    } else if (previous.current && !exit.intentional) setExpired(true);
    if (!token) {
      exit.intentional = false;
      hint.email = null;
    }
    previous.current = token;
  }, [token]);

  if (!token) {
    return <Login api={services.account} onSignedIn={(accessToken, email) => { hint.email = email; session.set(accessToken); }} notice={expired ? (exit.notice ?? t("errors.sessionExpired")) : undefined} />;
  }
  return <>{children}</>;
}