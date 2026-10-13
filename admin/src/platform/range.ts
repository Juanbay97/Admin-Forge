export type Days = 7 | 30 | 90;
export const RANGES: readonly Days[] = [7, 30, 90];

/** The `?days=` value, defaulting to 30 for anything that is not exactly one of the offered ranges. */
export function parseDays(value: string | null): Days {
  return RANGES.find((days) => String(days) === value) ?? 30;
}

const day = (date: Date) => date.toISOString().slice(0, 10);
const shifted = (date: Date, days: number) => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days));

export interface Window {
  from: string;
  to: string;
}

/** Inclusive UTC days ending today: the platform rolls usage up by UTC day. */
export function windowFor(days: Days, now: Date = new Date()): Window {
  return { from: day(shifted(now, -(days - 1))), to: day(shifted(now, 0)) };
}

/** The same number of days immediately before `windowFor(days)`. */
export function previousWindow(days: Days, now: Date = new Date()): Window {
  return { from: day(shifted(now, -(2 * days - 1))), to: day(shifted(now, -days)) };
}

export type Change = { direction: "up" | "down" | "flat"; percent: number } | { direction: "new"; percent: null };

export function changeOf(current: number, previous: number): Change {
  if (previous === 0) return current === 0 ? { direction: "flat", percent: 0 } : { direction: "new", percent: null };
  const percent = Math.round((Math.abs(current - previous) / previous) * 100);
  if (current === previous) return { direction: "flat", percent: 0 };
  return { direction: current > previous ? "up" : "down", percent };
}
