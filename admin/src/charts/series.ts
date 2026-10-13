// Colour is never the only encoding: series differ by token colour AND by dash pattern, and legends name each one.
export const STROKE_CLASS = ["stroke-chart-1", "stroke-chart-2", "stroke-chart-3", "stroke-chart-4", "stroke-chart-5"] as const;
export const FILL_CLASS = ["fill-chart-1", "fill-chart-2", "fill-chart-3", "fill-chart-4", "fill-chart-5"] as const;
export const BG_CLASS = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"] as const;
export const DASH = [undefined, "6 3", "2 3", "8 3 2 3", "1 4"] as const;

export const at = <T,>(list: readonly T[], index: number): T => list[index % list.length]!;

export interface LegendItem {
  label: string;
  /** Index into the chart palette. */
  color: number;
  detail?: string;
}