import { useState } from "react";
import type { Me } from "../api/account";
import type { Services } from "../api/services";
import { resolveEntry } from "../auth/access";
import { useOrgBranding } from "../brand/useOrgBranding";
import { Branding } from "../pages/Branding";
import { Catalog } from "../pages/Catalog";
import { Gateway } from "../pages/Gateway";
import { Members } from "../pages/Members";
import { Overview } from "../pages/Overview";
import { AccessDenied } from "./AccessDenied";

interface ConsoleProps {
  services: Services;
  me: Me;
  onSignOut: () => void;
}

const VIEWS = ["Overview", "Members", "Gateway", "Catalog", "Branding"] as const;
type View = (typeof VIEWS)[number];

export function Console({ services, me, onSignOut }: ConsoleProps) {
  const entry = resolveEntry(me);
  const [orgId, setOrgId] = useState(entry.kind === "ready" ? entry.organization.id : "");
  const [view, setView] = useState<View>("Overview");
  const { state: brand, theme, replace, reload } = useOrgBranding(services.branding, orgId);
  if (entry.kind === "denied") return <AccessDenied onSignOut={onSignOut} />;

  const organizations = entry.kind === "ready" ? [entry.organization] : entry.organizations;
  const selected = organizations.find((organization) => organization.id === orgId);

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-4 bg-primary px-6 py-3 text-sand">
        <img src={theme.assets.markOnDark} alt="" className="h-9 w-auto" />
        <span className="font-title text-lg font-bold">{theme.name}</span>
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
      <nav aria-label="Sections" className="flex gap-2 bg-teal px-6 py-2 text-white">
        {VIEWS.map((name) => (
          <button
            key={name}
            type="button"
            aria-current={view === name ? "page" : undefined}
            onClick={() => setView(name)}
            className="rounded px-3 py-1 transition-colors hover:bg-primary aria-[current=page]:bg-primary"
          >
            {name}
          </button>
        ))}
      </nav>
      <main className="mx-auto max-w-4xl p-6">
        {selected ? (
          brand.status === "loading" ? (
            <p role="status">Loading branding…</p>
          ) : view === "Branding" ? (
            brand.status === "ready" ? (
              <Branding key={selected.id} api={services.branding} organization={selected} branding={brand.branding} onChanged={replace} />
            ) : (
              <section className="flex flex-col gap-4">
                <h1 className="font-title text-2xl font-bold text-primary">Branding</h1>
                <p role="alert" className="font-medium text-red-800">
                  Branding could not be loaded. Try again.
                </p>
                <button
                  type="button"
                  onClick={reload}
                  className="self-start rounded border border-teal px-4 py-2 text-teal transition-colors hover:bg-teal hover:text-white"
                >
                  Try again
                </button>
              </section>
            )
          ) : view === "Members" ? (
            <Members key={selected.id} api={services.account} membersApi={services.members} organization={selected} />
          ) : view === "Catalog" ? (
            <Catalog key={selected.id} catalogApi={services.catalog} organization={selected} />
          ) : view === "Gateway" ? (
            <Gateway key={selected.id} gatewayApi={services.gateway} organization={selected} />
          ) : (
            <Overview key={selected.id} api={services.account} organization={selected} />
          )
        ) : (
          <p>Select an organization to continue.</p>
        )}
      </main>
    </div>
  );
}