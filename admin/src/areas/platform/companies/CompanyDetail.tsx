import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PauseCircle, PlayCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router";
import type { Company } from "../../../api/platform";
import { ApiError } from "../../../api/client";
import { NotFound } from "../../../components/NotFound";
import { TypedConfirm } from "../../../components/TypedConfirm";
import { setupChecklist } from "../../../platform/companies";
import { windowFor } from "../../../platform/range";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { PageHeader } from "../../../ui/PageHeader";
import { Skeleton } from "../../../ui/Skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../../ui/Tabs";
import { AlertDialog } from "../../../ui/overlay/Dialog";
import { useToast } from "../../../ui/toast/Toast";
import { OverviewTab } from "./OverviewTab";
import { companyTabs } from "./tabs";

export function CompanyDetail() {
  const { t } = useTranslation(["platform", "common"]);
  const { id = "" } = useParams();
  const { platform } = useServices();
  const company = useQuery({ queryKey: ["platform", "company", id], queryFn: () => platform.company(id), retry: false });
  if (company.isError && company.error instanceof ApiError && company.error.status === 404) return <NotFound />;
  if (company.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void company.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(company.error)}</Alert>;
  if (!company.data) return <div role="status" aria-label={t("companies.detail.loading")}><Skeleton className="h-10 w-64" /><Skeleton className="mt-6 h-40 w-full" /></div>;
  return <Detail company={company.data} />;
}

function Detail({ company }: { company: Company }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [suspending, setSuspending] = useState(false);
  const [reactivating, setReactivating] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const id = company.id;
  const window30 = windowFor(30);
  const keys = useQuery({ queryKey: ["platform", "company", id, "keys"], queryFn: () => platform.companyKeys(id) });
  const models = useQuery({ queryKey: ["platform", "company", id, "models"], queryFn: () => platform.modelAccess(id) });
  const branding = useQuery({ queryKey: ["platform", "company", id, "branding"], queryFn: () => platform.branding(id) });
  const usage = useQuery({ queryKey: ["platform", "usage", "companies", window30], queryFn: () => platform.usageByCompany(window30) });

  const changed = (message: string) => {
    void client.invalidateQueries({ queryKey: ["platform", "company", id] });
    void client.invalidateQueries({ queryKey: ["platform", "companies"] });
    toast.push({ tone: "success", title: message });
  };
  const suspend = useMutation({ mutationFn: () => platform.suspend(id), onSuccess: () => { setSuspending(false); setRefusal(null); changed(t("companies.detail.toast.suspended", { name: company.display_name })); }, onError: (error) => setRefusal(errorMessage(error)) });
  const reactivate = useMutation({ mutationFn: () => platform.reactivate(id), onSuccess: () => changed(t("companies.detail.toast.reactivated", { name: company.display_name })) });

  const checklist = keys.data && models.data && branding.data ? setupChecklist({ brandingRevision: branding.data.revision, keyCount: keys.data.keys.length, modelCount: models.data.models.length }) : null;
  const overview = (
    <OverviewTab
      data={{
        checklist,
        keyCount: keys.data?.keys.length ?? 0,
        modelCount: models.data?.models.length ?? 0,
        brandingRevision: branding.data?.revision ?? 0,
        usage: usage.isPending ? undefined : (usage.data?.companies.find((item) => item.organization_id === id) ?? null),
      }}
    />
  );
  const tabs = [{ id: "overview", label: t("companies.detail.tabs.overview"), render: () => overview }, ...companyTabs(company, t)];
  const selected = tabs.find((tab) => tab.id === params.get("tab"))?.id ?? "overview";

  return (
    <section className="flex flex-col gap-6">
      <PageHeader
        title={company.display_name}
        description={t("companies.detail.code", { slug: company.slug })}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={company.active ? "success" : "warning"}>{company.active ? t("companies.status.active") : t("companies.status.suspended")}</Badge>
            {company.active ? (
              <Button variant="outline" onClick={() => setSuspending(true)}><PauseCircle aria-hidden="true" className="size-4" />{t("companies.detail.suspend")}</Button>
            ) : (
              <Button onClick={() => setReactivating(true)}><PlayCircle aria-hidden="true" className="size-4" />{t("companies.detail.reactivate")}</Button>
            )}
          </div>
        }
      />
      {!company.active && <Alert tone="warning" title={t("companies.detail.suspendedTitle")}>{t("companies.detail.suspendedBody")}</Alert>}
      <Tabs value={selected} onValueChange={(value) => setParams((current) => { const next = new URLSearchParams(current); next.set("tab", value); return next; }, { replace: true })}>
        <TabsList aria-label={t("companies.detail.sections")} className="overflow-x-auto">
          {tabs.map((tab) => <TabsTrigger key={tab.id} value={tab.id}>{tab.label}</TabsTrigger>)}
        </TabsList>
        {tabs.map((tab) => <TabsContent key={tab.id} value={tab.id}>{tab.render()}</TabsContent>)}
      </Tabs>
      <TypedConfirm
        open={suspending}
        onOpenChange={(open) => { setSuspending(open); if (!open) setRefusal(null); }}
        title={t("companies.detail.suspendDialog.title", { name: company.display_name })}
        effect={t("companies.detail.suspendDialog.effect")}
        phrase={company.slug}
        confirmLabel={t("companies.detail.suspendDialog.confirm")}
        error={refusal}
        onConfirm={async () => { await suspend.mutateAsync().catch(() => undefined); }}
      />
      <AlertDialog open={reactivating} onOpenChange={setReactivating} title={t("companies.detail.reactivateDialog.title", { name: company.display_name })} description={t("companies.detail.reactivateDialog.description")} confirmLabel={t("companies.detail.reactivateDialog.confirm")} onConfirm={() => reactivate.mutateAsync().then(() => undefined)} />
    </section>
  );
}