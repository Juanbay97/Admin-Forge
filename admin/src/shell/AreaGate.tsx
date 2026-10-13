import { Navigate, Outlet } from "react-router";
import { AccessDenied } from "../components/AccessDenied";
import { NotFoundPage } from "./NotFoundPage";
import { enterableArea, type AreaManifest } from "./areas";
import { homeFor } from "./identity";
import { useIdentity } from "./IdentityBoundary";
import { useServices } from "./services";
import { signOut } from "./session";

/**
 * Guards one area by capability. A registered-but-disabled area is "not found" for everyone (its existence is not
 * advertised); a user without the capability sees AccessDenied.
 */
export function AreaGate({ area }: { area: AreaManifest }) {
  const identity = useIdentity();
  const services = useServices();
  if (!area.enabled) return <NotFoundPage />;
  if (!area.requires(identity)) return <AccessDenied onSignOut={() => void signOut(services)} />;
  return <Outlet />;
}

/** `/` sends the user to the home of their role, or tells them this console is not for them. */
export function HomeRedirect() {
  const identity = useIdentity();
  const services = useServices();
  const area = enterableArea(identity, homeFor(identity));
  if (!area) return <AccessDenied onSignOut={() => void signOut(services)} />;
  return <Navigate to={area.basePath} replace />;
}