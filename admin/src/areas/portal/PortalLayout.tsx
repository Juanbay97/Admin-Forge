import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useOutletContext } from "react-router";
import type { Organization } from "../../api/account";
import type { Services } from "../../api/services";
import { useOrgBranding, type BrandState } from "../../brand/useOrgBranding";
import { AccessDenied } from "../../components/AccessDenied";
import { AREAS } from "../../shell/areas";
import { AppShell } from "../../shell/AppShell";
import { useIdentity } from "../../shell/IdentityBoundary";
import { useServices } from "../../shell/services";
import { signOut } from "../../shell/session";
import { Select } from "../../ui/Select";

export interface PortalContext {
  services: Services;
  organization: Organization;
  brand: BrandState;
  /** The company code employees type in the desktop app, from the member's branding read. */
  code: string | null;
}

export const usePortal = () => useOutletContext<PortalContext>();

/** The member portal: one company at a time (a switcher when the account belongs to several), wearing that company's branding. */
export function PortalLayout() {
  const { t } = useTranslation(["portal", "common"]);
  const services = useServices();
  const identity = useIdentity();
  const organizations = identity.orgs;
  const [orgId, setOrgId] = useState(organizations[0]?.id ?? "");
  const { state: brand, theme } = useOrgBranding(services.branding, orgId);
  if (organizations.length === 0) return <AccessDenied onSignOut={() => void signOut(services)} message={t("layout.noCompany")} />;
  const selected = organizations.find((organization) => organization.id === orgId) ?? organizations[0]!;

  const switcher =
    organizations.length > 1 ? (
      <label className="flex items-center gap-2 text-body">
        <span className="hidden text-muted sm:inline">{t("layout.company")}</span>
        <span className="sr-only sm:hidden">{t("layout.company")}</span>
        <Select value={selected.id} onChange={(event) => setOrgId(event.target.value)} className="min-w-0 max-w-40 sm:max-w-56">
          {organizations.map((organization) => (
            <option key={organization.id} value={organization.id}>{organization.display_name}</option>
          ))}
        </Select>
      </label>
    ) : null;

  const context: PortalContext = { services, organization: selected, brand, code: brand.status === "ready" ? (brand.branding.code ?? null) : null };
  return (
    <AppShell area={AREAS.portal} brand={theme} switcher={switcher}>
      {brand.status === "loading" ? <p role="status">{t("layout.loading")}</p> : <Outlet context={context} key={selected.id} />}
    </AppShell>
  );
}