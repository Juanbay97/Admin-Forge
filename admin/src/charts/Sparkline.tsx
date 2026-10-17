import { useTranslation } from "react-i18next";
import { formatTokens } from "../lib/format";
import { buildLinePath } from "./path";
import { linearScale } from "./scale";

/** A tiny inline trend: an image with a label that names the last value. */
export function Sparkline({ values, label, format = formatTokens, width = 120, height = 32 }: {
  values: number[];
  label: string;
  format?: (value: number) => string;
  width?: number;
  height?: number;
}) {
  const { t } = useTranslation();
  const finite = values.filter(Number.isFinite);
  const last = finite[finite.length - 1];
  const x = linearScale([0, Math.max(1, values.length - 1)], [2, width - 2]);
  const y = linearScale([Math.min(0, ...finite), Math.max(1, ...finite)], [height - 2, 2]);
  const path = buildLinePath(values.map((value, index) => [x(index), y(value)] as const));
  return (
    <svg role="img" aria-label={t("charts.sparkline", { label, value: last === undefined ? t("charts.sparklineNone") : format(last) })} width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="inline-block align-middle">
      <path d={path} fill="none" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="stroke-chart-1" />
    </svg>
  );
}