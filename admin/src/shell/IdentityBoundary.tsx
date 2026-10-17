import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";
import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";
import { AccessDenied } from "../components/AccessDenied";
import { Spinner } from "../ui/Spinner";
import { AREAS } from "./areas";
import { loadIdentity, type Identity } from "./identity";
import { useServices } from "./services";
import { hint, signOut } from "./session";

const IdentityContext = createContext<Identity | null>(null);

/** For public pages that may or may not sit under the boundary. */
export const useIdentityOptional = (): Identity | null => useContext(IdentityContext);

export function useIdentity(): Identity {
  const identity = useContext(IdentityContext);
  if (!identity) throw new Error("useIdentity must be used under IdentityBoundary");
  return identity;
}

/** Loads who the signed-in account is once per session; every area route below it can rely on the identity. */
export function IdentityBoundary() {
  const { t } = useTranslation();
  const services = useServices();
  const query = useQuery({
    queryKey: ["shell", "identity"],
    queryFn: () => loadIdentity(services, { probePlatform: AREAS.platform.enabled, emailHint: hint.email }),
    staleTime: Infinity,
    retry: false,
  });
  if (query.isError) {
    return <AccessDenied title={t("shell.accountLoadFailedTitle")} message={t("shell.accountLoadFailed")} onSignOut={() => void signOut(services)} />;
  }
  if (!query.data) {
    return (
      <div className="p-8">
        <Spinner label={t("shell.loading")} />
      </div>
    );
  }
  return (
    <IdentityContext.Provider value={query.data}>
      <Outlet />
    </IdentityContext.Provider>
  );
}