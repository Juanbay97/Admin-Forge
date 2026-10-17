import { Activity, Info } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { BarChart } from "../../charts/BarChart";
import { RangePicker } from "../../components/usage/RangePicker";
import { useDays } from "../../components/usage/useDays";
import { formatCostMicros, formatNumber, formatTokens } from "../../lib/format";
import { windowFor } from "../../platform/range";
import { tokensOf } from "../../platform/usage";
import { errorMessage } from "../../shell/errors";
import { Alert } from "../../ui/Alert";
import { Button, buttonVariants } from "../../ui/Button";
import { EmptyState } from "../../ui/EmptyState";
import { PageHeader } from "../../ui/PageHeader";
import { Skeleton } from "../../ui/Skeleton";
import { Stat } from "../../ui/Stat";
import { usePortal } from "./PortalLayout";

export function Usage() {
  const { t } = useTranslation(["portal", "common"]);
  const { services, organization } = usePortal();
  const [days, setDays] = useDays();
  const window = windowFor(days);
  const usage = useQuery({ queryKey: ["portal", "usage", organization.id, window], queryFn: () => services.usage.mine(organization.id, window), retry: false });

  return (
    <section className="flex flex-col gap-6">
      <PageHeader title={t("usage.title")} description={t("usage.description")} actions={<RangePicker days={days} onChange={setDays} />} />
      {usage.isPending && <Skeleton className="h-40 w-full" />}
      {usage.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void usage.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(usage.error)}</Alert>}
      {usage.isSuccess && usage.data === null && (
        <EmptyState icon={Info} title={t("usage.notAvailableTitle")} hint={t("usage.notAvailableHint")} />
      )}
      {usage.data && usage.data.requests === 0 && (
        <EmptyState icon={Activity} title={t("usage.emptyTitle")} hint={t("usage.emptyHint")} action={<Link to="/portal/download" className={buttonVariants({})}>{t("common:download.title")}</Link>} />
      )}
      {usage.data && usage.data.requests > 0 && (
        <>
          <section aria-label={t("usage.label")}>
            <dl className="grid gap-4 sm:grid-cols-3">
              <Stat label={t("usage.tokens")}>{formatTokens(tokensOf(usage.data))}</Stat>
              <Stat label={t("usage.requests")}>{formatNumber(usage.data.requests)}</Stat>
              <Stat label={t("usage.cost")}>{formatCostMicros(usage.data.cost_micros)}</Stat>
            </dl>
          </section>
          <BarChart id="my-token-split" title={t("usage.splitTitle")} items={[{ label: t("usage.prompt"), value: usage.data.prompt_tokens }, { label: t("usage.completion"), value: usage.data.completion_tokens }]} />
        </>
      )}
    </section>
  );
}