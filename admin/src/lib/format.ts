// Pure display formatters shared by tables, cards and charts. None of them throws: a value that cannot be shown is a dash.
const NONE = "—";

const finite = (value: number): boolean => typeof value === "number" && Number.isFinite(value);

const COMPACT: ReadonlyArray<readonly [number, string]> = [
  [1_000_000_000, "B"],
  [1_000_000, "M"],
  [1_000, "K"],
];

/** 999 -> "999", 1_234 -> "1.2K", 1_234_567 -> "1.2M". */
export function formatTokens(count: number): string {
  if (!finite(count)) return NONE;
  const magnitude = Math.abs(count);
  for (const [size, suffix] of COMPACT) {
    if (magnitude >= size) return `${(count / size).toFixed(1).replace(/\.0$/, "")}${suffix}`;
  }
  return String(Math.round(count));
}

const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Integer micro-USD: 4_200 -> "$0.0042", 500_000 -> "$0.50", 1_234_560_000 -> "$1,234.56". */
export function formatCostMicros(micros: number): string {
  if (!finite(micros)) return NONE;
  const dollars = micros / 1_000_000;
  if (Math.abs(dollars) >= 1) return USD.format(dollars);
  const fixed = Math.abs(dollars).toFixed(4).replace(/(\.\d\d)0{1,2}$/, "$1").replace(/(\.\d\d\d)0$/, "$1");
  return `${dollars < 0 ? "-" : ""}$${Number(fixed) === 0 ? "0.00" : fixed}`;
}

/** A ratio (0.256) as a percentage ("26%", or "25.6%" with one digit). */
export function formatPercent(ratio: number, digits = 0): string {
  if (!finite(ratio)) return NONE;
  return `${(ratio * 100).toFixed(digits)}%`;
}

const DATE = new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC",
});

function parse(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "Oct 12, 2026" in UTC so the same value reads the same on every machine. */
export function formatDate(iso: string): string {
  const date = parse(iso);
  return date ? DATE.format(date) : NONE;
}

/** "Oct 12, 2026, 23:30 UTC". */
export function formatDateTime(iso: string): string {
  const date = parse(iso);
  return date ? `${DATE_TIME.format(date)} UTC` : NONE;
}
