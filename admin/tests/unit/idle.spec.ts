import { expect, test } from "@playwright/test";
import { createIdleTimer, IDLE_LIMIT_MS } from "../../src/shell/idle";

const clock = () => {
  let now = 0;
  const timers: Array<{ at: number; run: () => void; id: number }> = [];
  let next = 1;
  return {
    now: () => now,
    set: (run: () => void, ms: number) => (timers.push({ at: now + ms, run, id: next }), next++),
    clear: (id: unknown) => void timers.splice(timers.findIndex((timer) => timer.id === id), 1),
    advance(ms: number) {
      now += ms;
      for (const timer of timers.filter((candidate) => candidate.at <= now).sort((a, b) => a.at - b.at)) {
        timers.splice(timers.indexOf(timer), 1);
        timer.run();
      }
    },
  };
};

test.describe("idle timer", () => {
  test("signs out after thirty minutes without activity", () => {
    const time = clock();
    let expired = 0;
    createIdleTimer({ onIdle: () => expired++, set: time.set, clear: time.clear });
    time.advance(IDLE_LIMIT_MS - 1);
    expect(expired).toBe(0);
    time.advance(1);
    expect(expired).toBe(1);
    expect(IDLE_LIMIT_MS).toBe(30 * 60 * 1000);
  });
  test("any activity restarts the countdown, and stop cancels it", () => {
    const time = clock();
    let expired = 0;
    const idle = createIdleTimer({ onIdle: () => expired++, set: time.set, clear: time.clear });
    time.advance(IDLE_LIMIT_MS - 10);
    idle.touch();
    time.advance(IDLE_LIMIT_MS - 10);
    expect(expired).toBe(0);
    idle.stop();
    time.advance(IDLE_LIMIT_MS);
    expect(expired).toBe(0);
  });
});
