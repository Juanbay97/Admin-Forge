import { ArrowDownRight, ArrowRight, ArrowUpRight, Sparkles } from "lucide-react";
import type { Change } from "../../platform/range";
import { Badge } from "../../ui/Badge";

/** "+12%" against the previous period; `tone` says whether more is good (usage) or neutral. */
export function Delta({ change }: { change: Change }) {
  if (change.direction === "new") return <Badge tone="info"><Sparkles aria-hidden="true" className="size-3" />New</Badge>;
  if (change.direction === "flat") return <Badge tone="neutral"><ArrowRight aria-hidden="true" className="size-3" />No change</Badge>;
  const Icon = change.direction === "up" ? ArrowUpRight : ArrowDownRight;
  return (
    <Badge tone="neutral">
      <Icon aria-hidden="true" className="size-3" />
      {change.direction === "up" ? "+" : "−"}{change.percent}%<span className="sr-only"> versus the previous period</span>
    </Badge>
  );
}
