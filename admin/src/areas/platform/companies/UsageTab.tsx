import { Activity } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "../../../charts/BarChart";
import type { Company } from "../../../api/platform";
import { formatCostMicros, formatTokens } from "../../../lib/format";
import { changeOf, previousWindow, windowFor } from "../../../platform/range";
import { tokensOf } from "../../../platform/usage";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { EmptyState } from "../../../ui/EmptyState";
import { Skeleton } from "../../../ui/Skeleton";
import { Stat } from "../../../ui/Stat";
import { Delta } from "../Delta";
import { RangePicker } from "../RangePicker";
import { useDays } from "../useDays";

/** The platform reports usage per company per window (no per-day series, per-model or per-person view for a platform owner). */
export function UsageTab({ company }: { company: Company }) {
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
        <p className="text-body text-muted">Usage metered through the gateway for this company, by UTC day.</p>
        <RangePicker days={days} onChange={setDays} />
      </div>
      {now.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void now.refetch()}>Try again</Button>}>{errorMessage(now.error)}</Alert>}
      {now.isPending && <Skeleton className="h-40 w-full" />}
      {now.isSuccess && !row && <EmptyState icon={Activity} title="No usage yet" hint="Usage appears here after the company's members send their first request through the gateway." />}
      {row && (
        <>
          {row.unpriced_requests > 0 && <Alert tone="warning">{row.unpriced_requests} {row.unpriced_requests === 1 ? "request" : "requests"} had no model price; their cost is not included. Set prices under Prices.</Alert>}
          <section aria-label="Company usage">
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="Tokens"><span className="flex flex-wrap items-center gap-2">{formatTokens(tokensOf(row))}<Delta change={changeOf(tokensOf(row), earlier ? tokensOf(earlier) : 0)} /></span></Stat>
              <Stat label="Cost"><span className="flex flex-wrap items-center gap-2">{formatCostMicros(row.cost_micros)}<Delta change={changeOf(row.cost_micros, earlier?.cost_micros ?? 0)} /></span></Stat>
              <Stat label="Requests">{row.requests.toLocaleString("en-US")}</Stat>
              <Stat label="Failed requests">{row.error_requests.toLocaleString("en-US")}</Stat>
            </dl>
          </section>
          <BarChart
            id="company-token-split"
            title="Prompt and completion tokens"
            items={[{ label: "Prompt", value: row.prompt_tokens }, { label: "Completion", value: row.completion_tokens }]}
          />
          {row.estimated_requests > 0 && <p className="text-caption text-muted">{row.estimated_requests} {row.estimated_requests === 1 ? "request was" : "requests were"} measured by estimate because the gateway did not report usage.</p>}
        </>
      )}
    </section>
  );
}