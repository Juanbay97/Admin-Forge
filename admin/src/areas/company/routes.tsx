import { Branding } from "../../pages/Branding";
import { Catalog } from "../../pages/Catalog";
import { Gateway } from "../../pages/Gateway";
import { Members } from "../../pages/Members";
import { Overview } from "../../pages/Overview";
import { DownloadCard } from "../../components/DownloadCard";
import { DownloadPanel } from "../../components/DownloadPanel";
import { PageHeader } from "../../ui/PageHeader";
import { useCompany } from "./CompanyLayout";
import { UsageSection } from "./dashboard/UsageSection";

// The existing pages, mounted unchanged: each is keyed by the organization so a switch discards everything it held.
export function OverviewRoute() {
  const { services, organization, brand } = useCompany();
  return (
    <div className="flex flex-col gap-8" key={organization.id}>
      <Overview api={services.account} organization={organization} />
      <DownloadCard services={services} to="/company/download" code={brand.status === "ready" ? (brand.branding.code ?? null) : null} />
      <UsageSection services={services} organization={organization} />
    </div>
  );
}

export function MembersRoute() {
  const { services, organization } = useCompany();
  return <Members key={organization.id} api={services.account} membersApi={services.members} organization={organization} />;
}

export function GatewayRoute() {
  const { services, organization } = useCompany();
  return <Gateway key={organization.id} gatewayApi={services.gateway} organization={organization} />;
}

export function CatalogRoute() {
  const { services, organization } = useCompany();
  return <Catalog key={organization.id} catalogApi={services.catalog} organization={organization} />;
}

export function DownloadRoute() {
  const { services, organization, brand } = useCompany();
  return (
    <section key={organization.id} className="flex flex-col gap-6">
      <PageHeader title="Download Prometheon Forge" description={`Install Forge on your computer and connect it to ${organization.display_name}.`} />
      <DownloadPanel services={services} organization={organization} code={brand.status === "ready" ? (brand.branding.code ?? null) : null} />
    </section>
  );
}

export function BrandingRoute() {
  const { services, organization, brand, replaceBranding, reloadBranding } = useCompany();
  if (brand.status === "ready") {
    return <Branding key={organization.id} api={services.branding} organization={organization} branding={brand.branding} onChanged={replaceBranding} />;
  }
  return (
    <section className="flex flex-col gap-4">
      <h1 className="font-title text-2xl font-bold text-primary">Branding</h1>
      <p role="alert" className="font-medium text-red-800">
        Branding could not be loaded. Try again.
      </p>
      <button
        type="button"
        onClick={reloadBranding}
        className="self-start rounded border border-teal px-4 py-2 text-teal transition-colors hover:bg-teal hover:text-white"
      >
        Try again
      </button>
    </section>
  );
}