import { Check, CircleDashed } from "lucide-react";
import type { ReactNode } from "react";
import { Alert } from "../../../ui/Alert";
import { Card, CardContent, CardHeader, CardTitle } from "../../../ui/Card";
import { Skeleton } from "../../../ui/Skeleton";
import { Stat } from "../../../ui/Stat";
import { formatCostMicros, formatTokens } from "../../../lib/format";
import { tokensOf } from "../../../platform/usage";
import type { Checklist } from "../../../platform/companies";
import type { CompanyUsage } from "../../../api/platform";

export interface OverviewData {
  checklist: Checklist | null;
  keyCount: number;
  modelCount: number;
  brandingRevision: number;
  usage: CompanyUsage | null | undefined;
}

function Item({ done, label, detail }: { done: boolean; label: string; detail: ReactNode }) {
  return (
    <li className="flex items-center gap-3 py-2 text-body">
      {done ? <Check aria-hidden="true" className="size-5 shrink-0 text-on-ok-soft" /> : <CircleDashed aria-hidden="true" className="size-5 shrink-0 text-muted" />}
      <span className="font-medium text-fg">{label}</span>
      <span className="ml-auto text-right text-muted">{detail}</span>
    </li>
  );
}

export function OverviewTab({ data }: { data: OverviewData }) {
  const { checklist, usage } = data;
  return (
    <div className="flex flex-col gap-6">
      {checklist && !checklist.complete && (
        <Alert tone="warning" title="Finish setup">
          Members cannot use Forge until this company has at least one gateway key and a set of allowed models.
        </Alert>
      )}
      <section aria-label="Usage, last 30 days">
        <dl className="grid gap-4 sm:grid-cols-3">
          <Stat label="Tokens (30 days)">{usage === undefined ? <Skeleton className="h-6 w-16" /> : usage ? formatTokens(tokensOf(usage)) : "0"}</Stat>
          <Stat label="Cost (30 days)">{usage === undefined ? <Skeleton className="h-6 w-16" /> : usage ? formatCostMicros(usage.cost_micros) : "$0.00"}</Stat>
          <Stat label="Requests (30 days)">{usage === undefined ? <Skeleton className="h-6 w-16" /> : usage ? usage.requests.toLocaleString("en-US") : "0"}</Stat>
        </dl>
      </section>
      <section aria-label="Setup">
        <Card>
          <CardHeader>
            <CardTitle>Setup</CardTitle>
          </CardHeader>
          <CardContent>
            {checklist ? (
              <ul className="divide-y divide-line">
                <Item done={checklist.branding} label="Branding" detail={checklist.branding ? "Custom branding" : "Default Prometheon look (optional)"} />
                <Item done={checklist.keys} label="Gateway keys" detail={`${data.keyCount} assigned`} />
                <Item done={checklist.models} label="Models" detail={`${data.modelCount} allowed`} />
              </ul>
            ) : (
              <Skeleton className="h-24 w-full" />
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}