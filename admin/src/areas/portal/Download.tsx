import { useTranslation } from "react-i18next";
import { PageHeader } from "../../ui/PageHeader";
import { DownloadPanel } from "../../components/DownloadPanel";
import { usePortal } from "./PortalLayout";

export function Download() {
  const { t } = useTranslation();
  const { services, code, organization } = usePortal();
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title={t("download.title")} description={t("download.pageDescription", { name: organization.display_name })} />
      <DownloadPanel services={services} organization={organization} code={code} />
    </section>
  );
}
