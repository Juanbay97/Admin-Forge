import { Check, CircleDashed } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "../../../ui/Alert";
import { Card, CardContent, CardHeader, CardTitle } from "../../../ui/Card";
import { Skeleton } from "../../../ui/Skeleton";
import { Stat } from "../../../ui/Stat";
import { formatCostMicros, formatNumber, formatTokens } from "../../../lib/format";
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
  const { t } = useTranslation(["platform", "common"]);
  const { checklist, usage } = data;
  return (
    <div className="flex flex-col gap-6">
      {checklist && !checklist.complete && (
        <Alert tone="warning" title={t("companies.overviewTab.finishTitle")}>
          {t("companies.overviewTab.finishBody")}
        </Alert>
      )}
      <section aria-label={t("companies.overviewTab.usageLabel")}>
        <dl className="grid gap-4 sm:grid-cols-3">
          <Stat label={t("companies.overviewTab.tokens")}>{usage === undefined ? <Skeleton className="h-6 w-16" /> : usage ? formatTokens(tokensOf(usage)) : "0"}</Stat>
          <Stat label={t("companies.overviewTab.cost")}>{usage === undefined ? <Skeleton className="h-6 w-16" /> : formatCostMicros(usage ? usage.cost_micros : 0)}</Stat>
          <Stat label={t("companies.overviewTab.requests")}>{usage === undefined ? <Skeleton className="h-6 w-16" /> : formatNumber(usage ? usage.requests : 0)}</Stat>
        </dl>
      </section>
      <section aria-label={t("companies.overviewTab.setup")}>
        <Card>
          <CardHeader>
            <CardTitle>{t("companies.overviewTab.setup")}</CardTitle>
          </CardHeader>
          <CardContent>
            {checklist ? (
              <ul className="divide-y divide-line">
                <Item done={checklist.branding} label={t("companies.overviewTab.branding")} detail={checklist.branding ? t("companies.overviewTab.brandingCustom") : t("companies.overviewTab.brandingDefault")} />
                <Item done={checklist.keys} label={t("companies.overviewTab.keys")} detail={t("companies.overviewTab.keysAssigned", { count: data.keyCount })} />
                <Item done={checklist.models} label={t("companies.overviewTab.models")} detail={t("companies.overviewTab.modelsAllowed", { count: data.modelCount })} />
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