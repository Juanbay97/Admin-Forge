import { useEffect, useState, useSyncExternalStore } from "react";
import type { Me } from "./api/account";
import { services } from "./api/runtime";
import type { Services } from "./api/services";
import { session } from "./auth/session";
import { AccessDenied } from "./components/AccessDenied";
import { Console } from "./components/Console";
import { Login } from "./pages/Login";

export function App() {
  const token = useSyncExternalStore(session.subscribe, session.token);
  return token ? (
    <Workspace services={services} />
  ) : (
    <Login api={services.account} onSignedIn={(accessToken) => session.set(accessToken)} />
  );
}

async function signOut(services: Services) {
  try {
    await services.account.logout();
  } catch {
    // The token is dropped locally either way; the server expires it on its own.
  } finally {
    session.clear();
  }
}

function Workspace({ services }: { services: Services }) {
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let current = true;
    services.account.me().then(
      (loaded) => current && setMe(loaded),
      () => current && setFailed(true),
    );
    return () => {
      current = false;
    };
  }, [services]);

  const onSignOut = () => void signOut(services);
  if (failed) return <AccessDenied title="Something went wrong" message="Your account could not be loaded. Try again." onSignOut={onSignOut} />;
  if (!me) return <p role="status" className="p-8">Loading…</p>;
  return <Console services={services} me={me} onSignOut={onSignOut} />;
}
