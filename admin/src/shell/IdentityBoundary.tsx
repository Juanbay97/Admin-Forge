import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";
import { Outlet } from "react-router";
import { AccessDenied } from "../components/AccessDenied";
import { Spinner } from "../ui/Spinner";
import { AREAS } from "./areas";
import { loadIdentity, type Identity } from "./identity";
import { useServices } from "./services";
import { hint, signOut } from "./session";

const IdentityContext = createContext<Identity | null>(null);

export function useIdentity(): Identity {
  const identity = useContext(IdentityContext);
  if (!identity) throw new Error("useIdentity must be used under IdentityBoundary");
  return identity;
}

/** Loads who the signed-in account is once per session; every area route below it can rely on the identity. */
export function IdentityBoundary() {
  const services = useServices();
  const query = useQuery({
    queryKey: ["shell", "identity"],
    queryFn: () => loadIdentity(services, { probePlatform: AREAS.platform.enabled, emailHint: hint.email }),
    staleTime: Infinity,
    retry: false,
  });
  if (query.isError) {
    return <AccessDenied title="Something went wrong" message="Your account could not be loaded. Try again." onSignOut={() => void signOut(services)} />;
  }
  if (!query.data) {
    return (
      <div className="p-8">
        <Spinner label="Loading…" />
      </div>
    );
  }
  return (
    <IdentityContext.Provider value={query.data}>
      <Outlet />
    </IdentityContext.Provider>
  );
}