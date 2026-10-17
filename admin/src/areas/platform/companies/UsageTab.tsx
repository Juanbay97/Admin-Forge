import { Activity } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { BarChart } from "../../../charts/BarChart";
import type { Company } from "../../../api/platform";
import { formatCostMicros, formatNumber, formatTokens } from "../../../lib/format";
import { changeOf, previousWindow, windowFor } from "../../../platform/range";
import { tokensOf } from "../../../platform/usage";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { EmptyState } from "../../../ui/EmptyState";
import { Skeleton } from "../../../ui/Skeleton";
import { Stat } from "../../../ui/Stat";
import { Delta } from "../../../components/usage/Delta";
import { RangePicker } from "../../../components/usage/RangePicker";
import { useDays } from "../../../components/usage/useDays";

/** The platform reports usage per company per window (no per-day series, per-model or per-person view for a platform owner). */
export function UsageTab({ company }: { company: Company }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const [days, setDays] = useDays();
  const current = windowFor(days);
  const before = previousWindow(days);
  const now = useQuery({ queryKey: ["platform", "usage", "companies", current], queryFn: () => platform.usageByCompany(current) });
  const previous = useQuery({ queryKey: ["platform", "usage", "companies", before], queryFn: () => platform.usageByCompany(before) });
  const row = now.data?.companies.find((item) => item.organization_id === company.id);
  const earlier = previous.data?.companies.find((item) => item.organization_id === company.id);

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-body text-muted">{t("companies.usageTab.intro")}</p>
        <RangePicker days={days} onChange={setDays} />
      </div>
      {now.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void now.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(now.error)}</Alert>}
      {now.isPending && <Skeleton className="h-40 w-full" />}
      {now.isSuccess && !row && <EmptyState icon={Activity} title={t("companies.usageTab.emptyTitle")} hint={t("companies.usageTab.emptyHint")} />}
      {row && (
        <>
          {row.unpriced_requests > 0 && <Alert tone="warning">{t("companies.usageTab.unpriced", { count: row.unpriced_requests })}</Alert>}
          <section aria-label={t("companies.usageTab.usageLabel")}>
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label={t("companies.usageTab.tokens")}><span className="flex flex-wrap items-center gap-2">{formatTokens(tokensOf(row))}<Delta change={changeOf(tokensOf(row), earlier ? tokensOf(earlier) : 0)} /></span></Stat>
              <Stat label={t("companies.usageTab.cost")}><span className="flex flex-wrap items-center gap-2">{formatCostMicros(row.cost_micros)}<Delta change={changeOf(row.cost_micros, earlier?.cost_micros ?? 0)} /></span></Stat>
              <Stat label={t("companies.usageTab.requests")}>{formatNumber(row.requests)}</Stat>
              <Stat label={t("companies.usageTab.failed")}>{formatNumber(row.error_requests)}</Stat>
            </dl>
          </section>
          <BarChart
            id="company-token-split"
            title={t("companies.usageTab.splitTitle")}
            items={[{ label: t("companies.usageTab.prompt"), value: row.prompt_tokens }, { label: t("companies.usageTab.completion"), value: row.completion_tokens }]}
          />
          {row.estimated_requests > 0 && <p className="text-caption text-muted">{t("companies.usageTab.estimated", { count: row.estimated_requests })}</p>}
        </>
      )}
    </section>
  );
}