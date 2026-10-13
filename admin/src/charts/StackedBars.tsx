import { formatPercent, formatTokens } from "../lib/format";
import type { BarItem } from "./BarChart";
import { ChartFrame, type ChartFrameProps } from "./ChartFrame";
import { BG_CLASS, at } from "./series";

type Shared = Pick<ChartFrameProps, "id" | "title" | "loading" | "empty" | "emptyMessage" | "error" | "onRetry" | "className">;

/** One stacked bar showing each item's share of the total; the legend carries name and percentage, so colour is never alone. */
export function StackedBars({ items, format = formatTokens, ...frame }: Shared & { items: BarItem[]; format?: (value: number) => string }) {
  const ranked = [...items].sort((a, b) => b.value - a.value);
  const total = ranked.reduce((sum, item) => sum + item.value, 0);
  const share = (value: number) => (total > 0 ? value / total : 0);
  const summary = `${frame.title}: ${ranked.map((item) => `${item.label} ${formatPercent(share(item.value))}`).join(", ")}`;
  return (
    <ChartFrame
      {...frame}
      empty={frame.empty || total <= 0}
      legend={ranked.map((item, index) => ({ label: item.label, color: index, detail: formatPercent(share(item.value)) }))}
      table={{ columns: ["Item", "Value", "Share"], rows: ranked.map((item) => [item.label, format(item.value), formatPercent(share(item.value), 1)]) }}
    >
      {() => (
        <div role="img" aria-label={summary} className="flex h-6 w-full gap-0.5 overflow-hidden rounded-full">
          {ranked.map((item, index) => (
            <span key={item.label} className={at(BG_CLASS, index)} style={{ width: `${share(item.value) * 100}%` }} />
          ))}
        </div>
      )}
    </ChartFrame>
  );
}