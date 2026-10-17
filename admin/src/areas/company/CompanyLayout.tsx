import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useOutletContext } from "react-router";
import type { Organization } from "../../api/account";
import type { Services } from "../../api/services";
import { resolveEntry } from "../../auth/access";
import type { Branding } from "../../brand/branding";
import { useOrgBranding, type BrandState } from "../../brand/useOrgBranding";
import { AccessDenied } from "../../components/AccessDenied";
import { AREAS } from "../../shell/areas";
import { AppShell } from "../../shell/AppShell";
import { useIdentity } from "../../shell/IdentityBoundary";
import { useServices } from "../../shell/services";
import { signOut } from "../../shell/session";
import { Select } from "../../ui/Select";

export interface CompanyContext {
  services: Services;
  organization: Organization;
  brand: BrandState;
  replaceBranding: (branding: Branding) => void;
  reloadBranding: () => void;
}

export const useCompany = () => useOutletContext<CompanyContext>();

/**
 * The company administration area: one organization at a time (chosen from the topbar when the account administers
 * several), its branding applied to the shell, and the pages rendered through the router outlet.
 */
export function CompanyLayout() {
  const { t } = useTranslation(["company", "common"]);
  const services = useServices();
  const identity = useIdentity();
  const entry = resolveEntry({ account: identity.account, organizations: identity.orgs });
  const [orgId, setOrgId] = useState(entry.kind === "ready" ? entry.organization.id : "");
  const { state: brand, theme, replace, reload } = useOrgBranding(services.branding, orgId);
  if (entry.kind === "denied") return <AccessDenied onSignOut={() => void signOut(services)} />;

  const organizations = entry.kind === "ready" ? [entry.organization] : entry.organizations;
  const selected = organizations.find((organization) => organization.id === orgId);
  const switcher =
    organizations.length > 1 ? (
      <label className="flex items-center gap-2 text-body">
        <span className="hidden text-muted sm:inline">{t("layout.organization")}</span>
        <span className="sr-only sm:hidden">{t("layout.organization")}</span>
        <Select value={orgId} onChange={(event) => setOrgId(event.target.value)} className="min-w-0 max-w-40 sm:max-w-56">
          {!selected && <option value="">{t("layout.selectOrganization")}</option>}
          {organizations.map((organization) => (
            <option key={organization.id} value={organization.id}>
              {organization.display_name}
            </option>
          ))}
        </Select>
      </label>
    ) : null;

  const context: CompanyContext = { services, organization: selected!, brand, replaceBranding: replace, reloadBranding: reload };
  return (
    <AppShell area={AREAS.company} brand={theme} switcher={switcher}>
      {!selected ? (
        <p>{t("layout.selectToContinue")}</p>
      ) : brand.status === "loading" ? (
        <p role="status">{t("layout.loadingBranding")}</p>
      ) : (
        <Outlet context={context} />
      )}
    </AppShell>
  );
}