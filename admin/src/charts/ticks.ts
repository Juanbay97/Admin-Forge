// Pure axis helpers. Nothing here throws: flat, empty or non-finite input yields a usable axis.
const STEPS = [1, 2, 5];

/**
 * Round tick values covering [min, max] with at most `count + 1` ticks, on 1/2/5 x 10^n steps.
 * Flat series get a zero-based axis; NaN or infinite input yields [0, 1].
 */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  let low = Math.min(min, max);
  let high = Math.max(min, max);
  if (low === high) {
    if (low === 0) return [0, 1];
    [low, high] = low > 0 ? [0, low * 2] : [low * 2, 0];
  }
  const budget = Math.max(2, count) + 1;
  const magnitude = Math.floor(Math.log10(high - low));
  for (let power = magnitude - 1; power <= magnitude + 2; power++) {
    for (const base of STEPS) {
      const step = base * 10 ** power;
      const first = Math.floor(low / step);
      const last = Math.ceil(high / step);
      if (last - first + 1 <= budget) {
        return Array.from({ length: last - first + 1 }, (_, index) => Number(((first + index) * step).toPrecision(12)));
      }
    }
  }
  return [low, high];
}

const DAY = 86_400_000;
const DAY_STEPS = [1, 2, 3, 5, 7, 14, 30, 60, 90, 180, 365];
const TICK_LABEL = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export interface TimeTick {
  t: number;
  label: string;
}

/** Whole-day ticks from `start`, every N days with the smallest N that fits `maxTicks`; labels are UTC ("Oct 1"). */
export function timeTicks(start: number, end: number, maxTicks: number): TimeTick[] {
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return [];
  const span = (end - start) / DAY;
  const budget = Math.max(1, Math.floor(maxTicks));
  const step = DAY_STEPS.find((days) => Math.floor(span / days) + 1 <= budget) ?? DAY_STEPS[DAY_STEPS.length - 1]!;
  const ticks: TimeTick[] = [];
  for (let t = start; t <= end; t += step * DAY) ticks.push({ t, label: TICK_LABEL.format(t) });
  return ticks;
}

export const formatTick = (t: number): string => TICK_LABEL.format(t);