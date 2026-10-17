import { currentLanguage, localeOf } from "../i18n/config";

// Pure display formatters shared by tables, cards and charts. None of them throws: a value that cannot be shown is a dash.
// Numbers, dates and currency follow the active language (`Intl` with the chosen locale); `Intl` objects are cached per locale.
const NONE = "—";

const finite = (value: number): boolean => typeof value === "number" && Number.isFinite(value);

const cache = new Map<string, unknown>();
function cached<T>(key: string, create: () => T): T {
  if (!cache.has(key)) cache.set(key, create());
  return cache.get(key) as T;
}

/** A number in the active language's digits and separators (1234.5 -> "1,234.5" in English, "1234,5" in Spanish). */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  if (!finite(value)) return NONE;
  const locale = localeOf();
  return cached(`n|${locale}|${JSON.stringify(options ?? {})}`, () => new Intl.NumberFormat(locale, options)).format(value);
}

const COMPACT: ReadonlyArray<readonly [number, string]> = [
  [1_000_000_000, "B"],
  [1_000_000, "M"],
  [1_000, "K"],
];

/** 999 -> "999", 1_234 -> "1.2K", 1_234_567 -> "1.2M" (the decimal separator follows the language: "1,2K" in Spanish). */
export function formatTokens(count: number): string {
  if (!finite(count)) return NONE;
  const magnitude = Math.abs(count);
  for (const [size, suffix] of COMPACT) {
    if (magnitude >= size) return `${formatNumber(Number((count / size).toFixed(1)), { maximumFractionDigits: 1 })}${suffix}`;
  }
  return formatNumber(Math.round(count), { maximumFractionDigits: 0 });
}

/** Integer micro-USD: 4_200 -> "$0.0042", 500_000 -> "$0.50", 1_234_560_000 -> "$1,234.56" (Spanish: "0,0042 US$", "1234,56 US$"). */
export function formatCostMicros(micros: number): string {
  if (!finite(micros)) return NONE;
  const dollars = micros / 1_000_000;
  const small = Math.abs(dollars) < 1;
  // An amount that rounds to zero is shown as a plain zero, never as "-$0.00".
  const value = Math.abs(dollars) < 0.00005 ? 0 : dollars;
  return formatNumber(value, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: small ? 4 : 2 });
}

/** A ratio (0.256) as a percentage ("26%", or "25.6%" with one digit). */
export function formatPercent(ratio: number, digits = 0): string {
  if (!finite(ratio)) return NONE;
  return formatNumber(ratio, { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function dateFormat(kind: "date" | "dateTime" | "tick"): Intl.DateTimeFormat {
  const locale = localeOf();
  return cached(`d|${locale}|${kind}`, () =>
    new Intl.DateTimeFormat(
      locale,
      kind === "date"
        ? { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }
        : kind === "tick"
          ? { month: "short", day: "numeric", timeZone: "UTC" }
          : { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" },
    ),
  );
}

function parse(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "Oct 12, 2026" in UTC so the same value reads the same on every machine ("12 oct 2026" in Spanish). */
export function formatDate(iso: string): string {
  const date = parse(iso);
  return date ? dateFormat("date").format(date) : NONE;
}

/** "Oct 12, 2026, 23:30 UTC". */
export function formatDateTime(iso: string): string {
  const date = parse(iso);
  return date ? `${dateFormat("dateTime").format(date)} UTC` : NONE;
}

/** "Oct 1" / "1 oct": a chart axis day label, in UTC. */
export function formatDayLabel(epochMs: number): string {
  return dateFormat("tick").format(epochMs);
}

/** A collator for the active language, for sorting visible text. */
export function collator(): Intl.Collator {
  const language = currentLanguage();
  return cached(`c|${language}`, () => new Intl.Collator(language, { sensitivity: "base", numeric: true }));
}
