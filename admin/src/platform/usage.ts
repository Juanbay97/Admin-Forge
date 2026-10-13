interface Counters {
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export const tokensOf = (counters: Counters): number => counters.prompt_tokens + counters.completion_tokens;
export const requestsOf = (counters: Counters): number => counters.requests;

export interface DayCounters extends Counters {
  day: string;
  cost_micros: number;
  active_users: number;
}

interface Point {
  t: number;
  v: number;
}

/** One point per UTC day (at midnight UTC) for the chart kit: tokens, cost in micro-USD and active people. `hasUsage` is false for an all-zero range. */
export function dayPoints(days: readonly DayCounters[]): { tokens: Point[]; cost: Point[]; people: Point[]; hasUsage: boolean } {
  const at = (item: DayCounters) => Date.parse(`${item.day}T00:00:00Z`);
  return {
    tokens: days.map((item) => ({ t: at(item), v: tokensOf(item) })),
    cost: days.map((item) => ({ t: at(item), v: item.cost_micros })),
    people: days.map((item) => ({ t: at(item), v: item.active_users })),
    hasUsage: days.some((item) => item.requests > 0 || tokensOf(item) > 0),
  };
}
