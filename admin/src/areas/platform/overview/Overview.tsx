import { Building2, KeyRound, ScrollText } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router";
import { BarChart } from "../../../charts/BarChart";
import { AreaChart } from "../../../charts/TimeSeriesChart";
import { formatCostMicros, formatDateTime, formatNumber, formatTokens } from "../../../lib/format";
import { describeAction } from "../../../platform/audit";
import { changeOf, windowFor } from "../../../platform/range";
import { dayPoints, tokensOf } from "../../../platform/usage";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button, buttonVariants } from "../../../ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../ui/Card";
import { EmptyState } from "../../../ui/EmptyState";
import { PageHeader } from "../../../ui/PageHeader";
import { Skeleton } from "../../../ui/Skeleton";
import { Stat } from "../../../ui/Stat";
import { loadAllCompanies } from "../companies/data";
import { Delta } from "../../../components/usage/Delta";
import { RangePicker } from "../../../components/usage/RangePicker";
import { useDays } from "../../../components/usage/useDays";

export function Overview() {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const [days, setDays] = useDays();
  const current = windowFor(days);
  const overview = useQuery({ queryKey: ["platform", "overview", current], queryFn: () => platform.overview(current) });
  const series = useQuery({ queryKey: ["platform", "usage", "days", current], queryFn: () => platform.usageDays(current) });
  const byCompany = useQuery({ queryKey: ["platform", "usage", "companies", current], queryFn: () => platform.usageByCompany(current) });
  const byModel = useQuery({ queryKey: ["platform", "usage", "models", current], queryFn: () => platform.usageByModel(current) });
  const companies = useQuery({ queryKey: ["platform", "companies", "all"], queryFn: () => loadAllCompanies(platform) });
  const keys = useQuery({ queryKey: ["platform", "keys"], queryFn: () => platform.keys() });
  const audit = useQuery({ queryKey: ["platform", "audit", "tail"], queryFn: () => platform.audit({ page: 5 }) });

  const list = companies.data ?? [];
  const empty = companies.isSuccess && list.length === 0;
  if (empty) {
    return (
      <section className="flex flex-col gap-6">
        <PageHeader title={t("overview.title")} description={t("overview.description")} />
        <EmptyState
          icon={Building2}
          title={t("overview.firstCompanyTitle")}
          hint={t("overview.firstCompanyHint")}
          action={<Link to="/platform/companies/new" className={buttonVariants({})}>{t("overview.createCompany")}</Link>}
        />
      </section>
    );
  }

  const figures = overview.data;
  const tokens = figures ? tokensOf(figures) : 0;
  const previousTokens = figures ? tokensOf(figures.previous) : 0;
  const waiting = overview.isError ? "—" : <Skeleton className="h-6 w-16" />;
  const stats = (
    <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <Stat label={t("overview.stats.companies")}>
        {figures ? <span className="flex flex-wrap items-baseline gap-x-2"><span>{t("overview.stats.activeCompanies", { count: figures.companies.active })}</span><span className="text-body font-normal text-muted">{t("overview.stats.suspendedCompanies", { count: figures.companies.suspended })}</span></span> : overview.isError ? "—" : <Skeleton className="h-6 w-24" />}
      </Stat>
      <Stat label={t("overview.stats.activePeople")}>
        {figures ? <span className="flex flex-wrap items-center gap-2">{formatNumber(figures.active_users)}<Delta change={changeOf(figures.active_users, figures.previous.active_users)} /></span> : waiting}
      </Stat>
      <Stat label={t("overview.stats.requests")}>{figures ? formatNumber(figures.requests) : waiting}</Stat>
      <Stat label={t("overview.stats.tokens")}>
        {figures ? <span className="flex flex-wrap items-center gap-2">{formatTokens(tokens)}<Delta change={changeOf(tokens, previousTokens)} /></span> : waiting}
      </Stat>
      <Stat label={t("overview.stats.cost")}>
        {figures ? <span className="flex flex-wrap items-center gap-2">{formatCostMicros(figures.cost_micros)}<Delta change={changeOf(figures.cost_micros, figures.previous.cost_micros)} /></span> : waiting}
      </Stat>
    </dl>
  );
  const points = dayPoints(series.data?.days ?? []);

  const keyList = keys.data?.keys ?? [];
  const usable = keyList.filter((key) => key.status === "active" && key.has_key).length;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title={t("overview.title")} description={t("overview.description")} actions={<RangePicker days={days} onChange={setDays} />} />
      {overview.isError && (
        <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void overview.refetch()}>{t("common:actions.tryAgain")}</Button>}>
          {errorMessage(overview.error)}
        </Alert>
      )}
      {figures && figures.unpriced_requests > 0 && (
        <Alert tone="warning">{t("overview.unpriced", { count: figures.unpriced_requests })}</Alert>
      )}
      <section aria-label={t("overview.keyFigures")}>{stats}</section>
      <div className="grid gap-6 lg:grid-cols-2">
        <AreaChart
          id="tokens-per-day"
          title={t("overview.charts.tokensPerDay")}
          loading={series.isPending}
          error={series.isError ? errorMessage(series.error) : undefined}
          onRetry={() => void series.refetch()}
          empty={series.isSuccess && !points.hasUsage}
          emptyMessage={t("overview.charts.noUsage")}
          series={[{ id: "tokens", label: t("overview.charts.seriesTokens"), points: points.tokens }]}
        />
        <AreaChart
          id="cost-per-day"
          title={t("overview.charts.costPerDay")}
          loading={series.isPending}
          error={series.isError ? errorMessage(series.error) : undefined}
          onRetry={() => void series.refetch()}
          empty={series.isSuccess && !points.hasUsage}
          emptyMessage={t("overview.charts.noUsage")}
          format={formatCostMicros}
          series={[{ id: "cost", label: t("overview.charts.seriesCost"), points: points.cost }]}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <BarChart
          id="top-companies"
          title={t("overview.charts.topCompanies")}
          loading={byCompany.isPending}
          error={byCompany.isError ? errorMessage(byCompany.error) : undefined}
          onRetry={() => void byCompany.refetch()}
          empty={byCompany.isSuccess && byCompany.data.companies.length === 0}
          emptyMessage={t("overview.charts.noUsage")}
          format={formatCostMicros}
          items={(byCompany.data?.companies ?? []).slice(0, 10).map((company) => ({ label: company.display_name, value: company.cost_micros }))}
        />
        <BarChart
          id="tokens-by-model"
          title={t("overview.charts.tokensByModel")}
          loading={byModel.isPending}
          error={byModel.isError ? errorMessage(byModel.error) : undefined}
          onRetry={() => void byModel.refetch()}
          empty={byModel.isSuccess && byModel.data.models.length === 0}
          emptyMessage={t("overview.charts.noUsage")}
          items={(byModel.data?.models ?? []).map((model) => ({ label: model.upstream_id, value: tokensOf(model) }))}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label={t("overview.keyPool.title")}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><KeyRound aria-hidden="true" className="size-5 text-muted" />{t("overview.keyPool.title")}</CardTitle>
            </CardHeader>
            <CardContent>
              {keys.isPending ? <Skeleton className="h-6 w-40" /> : keys.isError ? (
                <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void keys.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(keys.error)}</Alert>
              ) : keyList.length === 0 ? (
                <p className="text-body text-muted"><Trans t={t} i18nKey="overview.keyPool.empty" components={{ link: <Link className="underline" to="/platform/keys" /> }} /></p>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={usable > 0 ? "success" : "warning"}>{t("overview.keyPool.active", { count: usable })}</Badge>
                  <Badge tone="neutral">{t("overview.keyPool.inactive", { count: keyList.length - usable })}</Badge>
                  <Link className="ml-auto text-body underline" to="/platform/keys">{t("overview.keyPool.manage")}</Link>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
        <section aria-label={t("overview.recent.title")}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><ScrollText aria-hidden="true" className="size-5 text-muted" />{t("overview.recent.title")}</CardTitle>
            </CardHeader>
            <CardContent>
              {audit.isPending ? <Skeleton className="h-16 w-full" /> : audit.isError ? (
                <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void audit.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(audit.error)}</Alert>
              ) : audit.data.entries.length === 0 ? (
                <p className="text-body text-muted">{t("overview.recent.none")}</p>
              ) : (
                <ul className="flex flex-col divide-y divide-line">
                  {audit.data.entries.map((entry) => (
                    <li key={entry.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-body">
                      <span className="font-medium text-fg">{describeAction(entry.action)}</span>
                      <time dateTime={entry.recorded_at} className="text-caption text-muted">{formatDateTime(entry.recorded_at)}</time>
                    </li>
                  ))}
                </ul>
              )}
              <Link className="mt-3 inline-block text-body underline" to="/platform/audit">{t("overview.recent.open")}</Link>
            </CardContent>
          </Card>
        </section>
      </div>
    </section>
  );
}
