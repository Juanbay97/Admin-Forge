import { useState } from "react";
import type { AccountApi, Me } from "../api/account";
import { resolveEntry } from "../auth/access";
import { defaultTheme } from "../brand/theme";
import { Overview } from "../pages/Overview";
import { AccessDenied } from "./AccessDenied";

interface ConsoleProps {
  api: AccountApi;
  me: Me;
  onSignOut: () => void;
}

export function Console({ api, me, onSignOut }: ConsoleProps) {
  const entry = resolveEntry(me);
  const [orgId, setOrgId] = useState(entry.kind === "ready" ? entry.organization.id : "");
  if (entry.kind === "denied") return <AccessDenied onSignOut={onSignOut} />;

  const organizations = entry.kind === "ready" ? [entry.organization] : entry.organizations;
  const selected = organizations.find((organization) => organization.id === orgId);

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-4 bg-primary px-6 py-3 text-sand">
        <img src={defaultTheme.assets.markOnDark} alt="" className="h-9 w-auto" />
        <span className="font-title text-lg font-bold">{defaultTheme.name}</span>
        {organizations.length > 1 && (
          <label className="flex items-center gap-2 text-sm">
            Organization
            <select
              value={orgId}
              onChange={(event) => setOrgId(event.target.value)}
              className="rounded bg-white px-2 py-1 text-carbon"
            >
              {!selected && <option value="">Select an organization…</option>}
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.display_name}
                </option>
              ))}
            </select>
          </label>
        )}
        <span className="ml-auto text-sm">{me.account.display_name}</span>
        <button
          type="button"
          onClick={onSignOut}
          className="rounded border border-sand px-3 py-1 text-sm transition-colors hover:bg-teal"
        >
          Sign out
        </button>
      </header>
      <main className="mx-auto max-w-4xl p-6">
        {selected ? (
          <Overview key={selected.id} api={api} organization={selected} />
        ) : (
          <p>Select an organization to continue.</p>
        )}
      </main>
    </div>
  );
}