import { Building2, KeyRound, ScrollText } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { BarChart } from "../../../charts/BarChart";
import { formatCostMicros, formatDateTime, formatTokens } from "../../../lib/format";
import { describeAction } from "../../../platform/audit";
import { changeOf, previousWindow, windowFor } from "../../../platform/range";
import { requestsOf, tokensOf } from "../../../platform/usage";
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
import { Delta } from "../Delta";
import { RangePicker } from "../RangePicker";
import { useDays } from "../useDays";

export function Overview() {
  const { platform } = useServices();
  const [days, setDays] = useDays();
  const current = windowFor(days);
  const before = previousWindow(days);
  const totals = useQuery({ queryKey: ["platform", "usage", "totals", current], queryFn: () => platform.usageTotals(current) });
  const previous = useQuery({ queryKey: ["platform", "usage", "totals", before], queryFn: () => platform.usageTotals(before) });
  const byCompany = useQuery({ queryKey: ["platform", "usage", "companies", current], queryFn: () => platform.usageByCompany(current) });
  const byModel = useQuery({ queryKey: ["platform", "usage", "models", current], queryFn: () => platform.usageByModel(current) });
  const companies = useQuery({ queryKey: ["platform", "companies", "all"], queryFn: () => platform.companies({ page: 100 }) });
  const keys = useQuery({ queryKey: ["platform", "keys"], queryFn: () => platform.keys() });
  const audit = useQuery({ queryKey: ["platform", "audit", "tail"], queryFn: () => platform.audit({ page: 5 }) });

  const list = companies.data?.companies ?? [];
  const active = list.filter((company) => company.active).length;
  const empty = companies.isSuccess && list.length === 0;
  if (empty) {
    return (
      <section className="flex flex-col gap-6">
        <PageHeader title="Platform overview" description="Companies, usage and gateway health across the platform." />
        <EmptyState
          icon={Building2}
          title="Create your first company"
          hint="Add a company, brand it, give it gateway keys and invite its first administrator. Usage appears here once its people start working."
          action={<Link to="/platform/companies/new" className={buttonVariants({})}>Create company</Link>}
        />
      </section>
    );
  }

  const tokens = totals.data ? tokensOf(totals.data) : 0;
  const previousTokens = previous.data ? tokensOf(previous.data) : 0;
  const stats = (
    <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Stat label="Companies">
        {companies.isPending ? <Skeleton className="h-6 w-24" /> : companies.isError ? "—" : <span className="flex flex-wrap items-baseline gap-x-2"><span>{active} active</span><span className="text-body font-normal text-muted">{list.length - active} suspended</span></span>}
      </Stat>
      <Stat label="Requests">{totals.data ? requestsOf(totals.data).toLocaleString("en-US") : totals.isError ? "—" : <Skeleton className="h-6 w-16" />}</Stat>
      <Stat label="Tokens">
        {totals.data && previous.data ? (
          <span className="flex flex-wrap items-center gap-2">{formatTokens(tokens)}<Delta change={changeOf(tokens, previousTokens)} /></span>
        ) : totals.isError ? "—" : <Skeleton className="h-6 w-16" />}
      </Stat>
      <Stat label="Cost">
        {totals.data && previous.data ? (
          <span className="flex flex-wrap items-center gap-2">{formatCostMicros(totals.data.cost_micros)}<Delta change={changeOf(totals.data.cost_micros, previous.data.cost_micros)} /></span>
        ) : totals.isError ? "—" : <Skeleton className="h-6 w-16" />}
      </Stat>
    </dl>
  );

  const keyList = keys.data?.keys ?? [];
  const usable = keyList.filter((key) => key.status === "active" && key.has_key).length;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Platform overview" description="Companies, usage and gateway health across the platform." actions={<RangePicker days={days} onChange={setDays} />} />
      {totals.isError && (
        <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => { void totals.refetch(); void previous.refetch(); }}>Try again</Button>}>
          {errorMessage(totals.error)}
        </Alert>
      )}
      {totals.data && totals.data.unpriced_requests > 0 && (
        <Alert tone="warning">{totals.data.unpriced_requests.toLocaleString("en-US")} {totals.data.unpriced_requests === 1 ? "request" : "requests"} in this range had no model price, so the cost shown does not include {totals.data.unpriced_requests === 1 ? "it" : "them"}. Set prices under Prices.</Alert>
      )}
      <section aria-label="Key figures">{stats}</section>
      <div className="grid gap-6 lg:grid-cols-2">
        <BarChart
          id="top-companies"
          title="Top companies by cost"
          loading={byCompany.isPending}
          error={byCompany.isError ? errorMessage(byCompany.error) : undefined}
          onRetry={() => void byCompany.refetch()}
          empty={byCompany.isSuccess && byCompany.data.companies.length === 0}
          emptyMessage="No usage yet"
          format={formatCostMicros}
          items={(byCompany.data?.companies ?? []).slice(0, 10).map((company) => ({ label: company.display_name, value: company.cost_micros }))}
        />
        <BarChart
          id="tokens-by-model"
          title="Tokens by model"
          loading={byModel.isPending}
          error={byModel.isError ? errorMessage(byModel.error) : undefined}
          onRetry={() => void byModel.refetch()}
          empty={byModel.isSuccess && byModel.data.models.length === 0}
          emptyMessage="No usage yet"
          items={(byModel.data?.models ?? []).map((model) => ({ label: model.upstream_id, value: tokensOf(model) }))}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label="Gateway key pool">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><KeyRound aria-hidden="true" className="size-5 text-muted" />Gateway key pool</CardTitle>
            </CardHeader>
            <CardContent>
              {keys.isPending ? <Skeleton className="h-6 w-40" /> : keys.isError ? (
                <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void keys.refetch()}>Try again</Button>}>{errorMessage(keys.error)}</Alert>
              ) : keyList.length === 0 ? (
                <p className="text-body text-muted">No keys yet. <Link className="underline" to="/platform/keys">Add the first key</Link> so companies can reach the gateway.</p>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={usable > 0 ? "success" : "warning"}>{usable} active</Badge>
                  <Badge tone="neutral">{keyList.length - usable} disabled or empty</Badge>
                  <Link className="ml-auto text-body underline" to="/platform/keys">Manage keys</Link>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
        <section aria-label="Recent activity">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><ScrollText aria-hidden="true" className="size-5 text-muted" />Recent activity</CardTitle>
            </CardHeader>
            <CardContent>
              {audit.isPending ? <Skeleton className="h-16 w-full" /> : audit.isError ? (
                <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void audit.refetch()}>Try again</Button>}>{errorMessage(audit.error)}</Alert>
              ) : audit.data.entries.length === 0 ? (
                <p className="text-body text-muted">Nothing recorded yet.</p>
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
              <Link className="mt-3 inline-block text-body underline" to="/platform/audit">Open the audit log</Link>
            </CardContent>
          </Card>
        </section>
      </div>
    </section>
  );
}
