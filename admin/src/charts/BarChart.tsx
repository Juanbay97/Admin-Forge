import { formatTokens } from "../lib/format";
import { ChartFrame, type ChartFrameProps } from "./ChartFrame";
import { BG_CLASS, at } from "./series";

export interface BarItem {
  label: string;
  value: number;
}
type Shared = Pick<ChartFrameProps, "id" | "title" | "loading" | "empty" | "emptyMessage" | "error" | "onRetry" | "className">;

/** Horizontal ranked bars with the value printed on each row; widths are CSSOM percentages, never injected CSS. */
export function BarChart({ items, format = formatTokens, ...frame }: Shared & { items: BarItem[]; format?: (value: number) => string }) {
  const ranked = [...items].sort((a, b) => b.value - a.value);
  const top = Math.max(1, ...ranked.map((item) => item.value));
  const total = ranked.reduce((sum, item) => sum + item.value, 0);
  const peak = ranked[0];
  const summary = peak ? `${frame.title}: ${ranked.length} items, total ${format(total)}, top ${peak.label} ${format(peak.value)}` : `${frame.title}: no data`;
  return (
    <ChartFrame {...frame} empty={frame.empty || ranked.length === 0} table={{ columns: ["Item", "Value"], rows: ranked.map((item) => [item.label, item.value.toLocaleString("en-US")]) }}>
      {() => (
        <div role="img" aria-label={summary} className="flex flex-col gap-2">
          {ranked.map((item) => (
            <div key={item.label} className="grid grid-cols-[minmax(6rem,10rem)_1fr_auto] items-center gap-3 text-body">
              <span data-testid="bar-label" className="truncate text-fg" title={item.label}>{item.label}</span>
              <span className="h-3 overflow-hidden rounded-full bg-subtle">
                <span className={`block h-full rounded-full ${at(BG_CLASS, 0)}`} style={{ width: `${Math.max(1, (item.value / top) * 100)}%` }} />
              </span>
              <span data-testid="bar-value" className="min-w-14 text-right tabular-nums text-muted">{format(item.value)}</span>
            </div>
          ))}
        </div>
      )}
    </ChartFrame>
  );
}