import { useState, type KeyboardEvent, type PointerEvent } from "react";
import { cn } from "../lib/cn";
import { formatTokens } from "../lib/format";
import { ChartFrame, type ChartFrameProps } from "./ChartFrame";
import { buildAreaPath, buildLinePath } from "./path";
import { linearScale } from "./scale";
import { DASH, FILL_CLASS, STROKE_CLASS, at } from "./series";
import { formatTick, niceTicks, timeTicks } from "./ticks";

export interface TimePoint {
  t: number;
  v: number;
}
export interface TimeSeries {
  id: string;
  label: string;
  points: TimePoint[];
}

type Shared = Pick<ChartFrameProps, "id" | "title" | "loading" | "empty" | "emptyMessage" | "error" | "onRetry" | "className">;
interface TimeSeriesProps extends Shared {
  series: TimeSeries[];
  /** Formats a value for ticks, the tooltip, the summary and the table. Defaults to compact token counts. */
  format?: (value: number) => string;
  area?: boolean;
}

const MARGIN = { left: 48, right: 12, top: 12, bottom: 28 };

function summarize(title: string, series: TimeSeries[], format: (value: number) => string): string {
  const all = series.flatMap((entry) => entry.points);
  if (all.length === 0) return `${title}: no data`;
  const times = all.map((point) => point.t);
  const total = all.reduce((sum, point) => sum + point.v, 0);
  const peak = all.reduce((best, point) => (point.v > best.v ? point : best));
  return `${title}: ${formatTick(Math.min(...times))} to ${formatTick(Math.max(...times))}, total ${format(total)}, peak ${format(peak.v)} on ${formatTick(peak.t)}`;
}

/** Time series as an area or line chart: nice y ticks, at most six date ticks, a crosshair on hover and with the arrow keys. */
export function TimeSeriesChart({ series, format = formatTokens, area = true, ...frame }: TimeSeriesProps) {
  const [active, setActive] = useState<number | null>(null);
  const lead = series[0]?.points ?? [];
  const times = lead.map((point) => point.t);
  const table = {
    columns: ["Date", ...series.map((entry) => entry.label)],
    rows: lead.map((point, index) => [formatTick(point.t), ...series.map((entry) => format(entry.points[index]?.v ?? Number.NaN))]),
  };
  const move = (event: KeyboardEvent) => {
    const last = lead.length - 1;
    const keys: Record<string, number | null | undefined> = {
      ArrowRight: active === null ? 0 : Math.min(last, active + 1),
      ArrowLeft: active === null ? last : Math.max(0, active - 1),
      Home: 0,
      End: last,
      Escape: null,
    };
    if (!(event.key in keys)) return;
    event.preventDefault();
    setActive(keys[event.key] ?? null);
  };
  const liveText = active === null || !lead[active]
    ? ""
    : `${formatTick(lead[active]!.t)}: ${series.map((entry) => `${entry.label} ${format(entry.points[active]?.v ?? Number.NaN)}`).join(", ")}`;

  return (
    <ChartFrame
      {...frame}
      empty={frame.empty || lead.length === 0}
      table={table}
      legend={series.length > 1 ? series.map((entry, index) => ({ label: entry.label, color: index })) : undefined}
    >
      {({ width, height, compact }) => {
        const left = compact ? 8 : MARGIN.left;
        const plotWidth = Math.max(1, width - left - MARGIN.right);
        const plotHeight = height - MARGIN.top - MARGIN.bottom;
        const maxV = Math.max(0, ...series.flatMap((entry) => entry.points.map((point) => point.v)));
        const yTicks = niceTicks(0, maxV, 4);
        const yTop = yTicks[yTicks.length - 1]!;
        const x = linearScale([Math.min(...times), Math.max(...times)], [left, left + plotWidth]);
        const y = linearScale([0, yTop], [MARGIN.top + plotHeight, MARGIN.top]);
        const xTicks = compact ? [] : timeTicks(Math.min(...times), Math.max(...times), Math.min(6, Math.max(2, Math.floor(plotWidth / 72))));
        const nearest = (clientX: number, box: DOMRect) => {
          const target = Math.min(Math.max(clientX - box.left, left), left + plotWidth);
          return times.reduce((best, t, index) => (Math.abs(x(t) - target) < Math.abs(x(times[best]!) - target) ? index : best), 0);
        };
        const marker = active === null ? null : lead[active];
        return (
          <div
            role="group"
            tabIndex={0}
            aria-label={`${frame.title} chart. Use the arrow keys to inspect each point.`}
            onKeyDown={move}
            onBlur={() => setActive(null)}
            className="relative rounded-control outline-focus focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            <svg
              role="img"
              aria-label={summarize(frame.title, series, format)}
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              className="block max-w-full touch-pan-y"
              onPointerMove={(event: PointerEvent<SVGSVGElement>) => setActive(nearest(event.clientX, event.currentTarget.getBoundingClientRect()))}
              onPointerLeave={() => setActive(null)}
            >
              {yTicks.map((tick) => (
                <g key={tick}>
                  <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} className="stroke-line" strokeWidth={1} />
                  {!compact && <text x={left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-muted text-caption">{format(tick)}</text>}
                </g>
              ))}
              {xTicks.map((tick) => (
                <text key={tick.t} data-testid="x-tick" x={x(tick.t)} y={height - 8} textAnchor="middle" className="fill-muted text-caption">{tick.label}</text>
              ))}
              {series.map((entry, index) => {
                const points = entry.points.map((point) => [x(point.t), y(point.v)] as const);
                return (
                  <g key={entry.id}>
                    {area && series.length === 1 && <path d={buildAreaPath(points, MARGIN.top + plotHeight)} className={at(FILL_CLASS, index)} fillOpacity={0.12} stroke="none" />}
                    <path data-series={entry.id} d={buildLinePath(points)} fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" strokeDasharray={at(DASH, index)} className={at(STROKE_CLASS, index)} />
                  </g>
                );
              })}
              {marker && (
                <g>
                  <line data-testid="crosshair" x1={x(marker.t)} x2={x(marker.t)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} className="stroke-line-strong" strokeDasharray="3 3" />
                  {series.map((entry, index) => {
                    const point = entry.points[active!];
                    return point ? <circle key={entry.id} cx={x(point.t)} cy={y(point.v)} r={4} className={cn("stroke-surface", at(FILL_CLASS, index))} strokeWidth={2} /> : null;
                  })}
                </g>
              )}
            </svg>
            {marker && (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute top-2 z-10 rounded-control border border-line bg-raised px-2.5 py-1.5 text-caption text-fg shadow-overlay"
                style={{ left: Math.min(Math.max(x(marker.t) + 10, 0), Math.max(0, width - 150)) }}
              >
                <p className="font-semibold">{formatTick(marker.t)}</p>
                {series.map((entry) => <p key={entry.id}>{entry.label}: {format(entry.points[active!]?.v ?? Number.NaN)}</p>)}
              </div>
            )}
            <div aria-live="polite" className="sr-only">{liveText}</div>
          </div>
        );
      }}
    </ChartFrame>
  );
}

export const AreaChart = TimeSeriesChart;
export function LineChart(props: Omit<TimeSeriesProps, "area">) {
  return <TimeSeriesChart {...props} area={false} />;
}