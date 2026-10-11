import { useEffect, useState, useSyncExternalStore } from "react";
import { type AccountApi, type Me } from "./api/account";
import { accountApi } from "./api/runtime";
import { session } from "./auth/session";
import { AccessDenied } from "./components/AccessDenied";
import { Console } from "./components/Console";
import { Login } from "./pages/Login";

export function App() {
  const token = useSyncExternalStore(session.subscribe, session.token);
  return token ? (
    <Workspace api={accountApi} />
  ) : (
    <Login api={accountApi} onSignedIn={(accessToken) => session.set(accessToken)} />
  );
}

async function signOut(api: AccountApi) {
  try {
    await api.logout();
  } catch {
    // The token is dropped locally either way; the server expires it on its own.
  } finally {
    session.clear();
  }
}

function Workspace({ api }: { api: AccountApi }) {
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let current = true;
    api.me().then(
      (loaded) => current && setMe(loaded),
      () => current && setFailed(true),
    );
    return () => {
      current = false;
    };
  }, [api]);

  const onSignOut = () => void signOut(api);
  if (failed) return <AccessDenied title="Something went wrong" message="Your account could not be loaded. Try again." onSignOut={onSignOut} />;
  if (!me) return <p role="status" className="p-8">Loading…</p>;
  return <Console api={api} me={me} onSignOut={onSignOut} />;
}