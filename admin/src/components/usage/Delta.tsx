import { ArrowDownRight, ArrowRight, ArrowUpRight, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatNumber } from "../../lib/format";
import type { Change } from "../../platform/range";
import { Badge } from "../../ui/Badge";

/** "+12%" against the previous period; `tone` says whether more is good (usage) or neutral. */
export function Delta({ change }: { change: Change }) {
  const { t } = useTranslation();
  if (change.direction === "new") return <Badge tone="info"><Sparkles aria-hidden="true" className="size-3" />{t("usage.delta.new")}</Badge>;
  if (change.direction === "flat") return <Badge tone="neutral"><ArrowRight aria-hidden="true" className="size-3" />{t("usage.delta.flat")}</Badge>;
  const Icon = change.direction === "up" ? ArrowUpRight : ArrowDownRight;
  return (
    <Badge tone="neutral">
      <Icon aria-hidden="true" className="size-3" />
      {change.direction === "up" ? "+" : "−"}{formatNumber(change.percent)}%<span className="sr-only"> {t("usage.delta.versusPrevious")}</span>
    </Badge>
  );
}
