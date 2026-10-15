import { PageHeader } from "../../ui/PageHeader";
import { DownloadPanel } from "../../components/DownloadPanel";
import { usePortal } from "./PortalLayout";

export function Download() {
  const { services, code, organization } = usePortal();
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Download Prometheon Forge" description={`Install Forge on your computer and connect it to ${organization.display_name}.`} />
      <DownloadPanel services={services} organization={organization} code={code} />
    </section>
  );
}
