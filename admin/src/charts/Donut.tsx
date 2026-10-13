import { formatPercent, formatTokens } from "../lib/format";
import type { BarItem } from "./BarChart";
import { ChartFrame, type ChartFrameProps } from "./ChartFrame";
import { STROKE_CLASS, at } from "./series";

type Shared = Pick<ChartFrameProps, "id" | "title" | "loading" | "empty" | "emptyMessage" | "error" | "onRetry" | "className">;
const MAX_SEGMENTS = 6;

/** The largest items (at most six) as ring segments; everything else folds into "Other". Segment lengths use pathLength=100. */
export function Donut({ items, format = formatTokens, ...frame }: Shared & { items: BarItem[]; format?: (value: number) => string }) {
  const ranked = [...items].filter((item) => item.value > 0).sort((a, b) => b.value - a.value);
  const rest = ranked.slice(MAX_SEGMENTS).reduce((sum, item) => sum + item.value, 0);
  const segments: BarItem[] = [...ranked.slice(0, MAX_SEGMENTS), ...(rest > 0 ? [{ label: "Other", value: rest }] : [])];
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  const summary = `${frame.title}: ${segments.map((item) => `${item.label} ${formatPercent(item.value / total)}`).join(", ")}`;
  const size = 160;
  const radius = 60;
  let offset = 0;
  return (
    <ChartFrame
      {...frame}
      empty={frame.empty || total <= 0}
      legend={segments.map((item, index) => ({ label: item.label, color: index, detail: formatPercent(item.value / total) }))}
      table={{ columns: ["Item", "Value", "Share"], rows: segments.map((item) => [item.label, format(item.value), formatPercent(item.value / total, 1)]) }}
    >
      {() => (
        <svg role="img" aria-label={summary} width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="mx-auto block">
          <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
            {segments.map((item, index) => {
              const length = (item.value / total) * 100;
              const circle = (
                <circle
                  key={item.label}
                  data-segment={item.label}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  strokeWidth={22}
                  pathLength={100}
                  strokeDasharray={`${Math.max(0, length - 0.6)} ${100 - Math.max(0, length - 0.6)}`}
                  strokeDashoffset={-offset}
                  strokeOpacity={item.label === "Other" ? 0.45 : index >= 5 ? 0.6 : 1}
                  className={at(STROKE_CLASS, item.label === "Other" ? 2 : index)}
                />
              );
              offset += length;
              return circle;
            })}
          </g>
          <text x={size / 2} y={size / 2} textAnchor="middle" dy="-0.1em" className="fill-fg text-card font-semibold">{format(total)}</text>
          <text x={size / 2} y={size / 2} textAnchor="middle" dy="1.3em" className="fill-muted text-caption">total</text>
        </svg>
      )}
    </ChartFrame>
  );
}