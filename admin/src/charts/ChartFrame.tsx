import { BarChart3 } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import { BG_CLASS, at, type LegendItem } from "./series";
import { useElementWidth } from "./useElementWidth";

export const MIN_HEIGHT = 160;
/** Under this width a chart drops axes and legends and leans on its table. */
export const COMPACT_WIDTH = 360;

export interface ChartTable {
  columns: string[];
  rows: Array<Array<string | number>>;
}

export interface ChartFrameProps {
  /** Stable id for tests and anchors, rendered as data-chart. */
  id: string;
  title: string;
  table: ChartTable;
  legend?: LegendItem[];
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  /** A failure message; shown as an alert with an optional retry. */
  error?: string;
  onRetry?: () => void;
  className?: string;
  children: (size: { width: number; height: number; compact: boolean }) => ReactNode;
}

/**
 * Shared chrome of every chart: sizes the drawing from its container (ResizeObserver), renders the loading, empty and
 * error variants, the legend with markers, and the visually hidden data table that mirrors the drawing for screen readers.
 */
export function ChartFrame({ id, title, table, legend, loading, empty, emptyMessage = "No data", error, onRetry, className, children }: ChartFrameProps) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const height = Math.min(320, Math.max(MIN_HEIGHT, Math.round(width * 0.4)));
  const state = error ? "error" : loading ? "loading" : empty ? "empty" : "ready";
  return (
    <figure data-chart={id} className={cn("flex min-w-0 flex-col gap-3", className)}>
      <figcaption className="font-title text-card font-semibold text-fg">{title}</figcaption>
      <div ref={ref} className="w-full min-w-0">
        {state === "loading" && (
          <div role="status" aria-label={`Loading ${title}`}>
            <Skeleton className="w-full" style={{ height: MIN_HEIGHT }} />
          </div>
        )}
        {state === "empty" && (
          <div className="flex flex-col items-center justify-center gap-2 rounded-card border border-dashed border-line-strong text-muted" style={{ minHeight: MIN_HEIGHT }}>
            <BarChart3 aria-hidden="true" className="size-6" />
            <p className="text-body">{emptyMessage}</p>
          </div>
        )}
        {state === "error" && (
          <Alert tone="destructive" title={error} action={onRetry ? <Button size="sm" variant="outline" onClick={onRetry}>Try again</Button> : undefined} />
        )}
        {state === "ready" && width > 0 && children({ width, height, compact: width < COMPACT_WIDTH })}
      </div>
      {state === "ready" && legend && legend.length > 0 && (
        <ul aria-label="Legend" className="flex flex-wrap gap-x-4 gap-y-1 text-caption text-fg">
          {legend.map((item) => (
            <li key={item.label} className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className={cn("size-2.5 rounded-sm", at(BG_CLASS, item.color))} />
              {item.label}
              {item.detail && <span className="text-muted">{item.detail}</span>}
            </li>
          ))}
        </ul>
      )}
      {state === "ready" && (
        <table className="sr-only">
          <caption>{title} data</caption>
          <thead>
            <tr>{table.columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr>
          </thead>
          <tbody>
            {table.rows.map((row, index) => (
              <tr key={index}>{row.map((cell, cellIndex) => (cellIndex === 0 ? <th key={cellIndex} scope="row">{cell}</th> : <td key={cellIndex}>{cell}</td>))}</tr>
            ))}
          </tbody>
        </table>
      )}
    </figure>
  );
}