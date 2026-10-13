import { expect, test } from "@playwright/test";
import { createToastStore } from "../../src/ui/toast/store";

/** A scheduler the test drives by hand. */
function manualClock() {
  const timers = new Map<number, { run: () => void; ms: number }>();
  let next = 1;
  return {
    schedule(run: () => void, ms: number) {
      const id = next++;
      timers.set(id, { run, ms });
      return () => void timers.delete(id);
    },
    pending: () => [...timers.values()].map((timer) => timer.ms),
    fireAll() {
      for (const [id, timer] of [...timers]) {
        timers.delete(id);
        timer.run();
      }
    },
  };
}

test.describe("toast store", () => {
  test("push adds newest last and notifies subscribers", () => {
    const store = createToastStore();
    const seen: number[] = [];
    store.subscribe(() => seen.push(store.list().length));
    store.push({ tone: "success", title: "Saved" });
    store.push({ tone: "info", title: "Synced", message: "3 models" });
    expect(store.list().map((toast) => toast.title)).toEqual(["Saved", "Synced"]);
    expect(store.list()[1]?.message).toBe("3 models");
    expect(seen).toEqual([1, 2]);
  });

  test("dismiss removes one toast and an unknown id is ignored", () => {
    const store = createToastStore();
    const first = store.push({ tone: "info", title: "One" });
    store.push({ tone: "info", title: "Two" });
    store.dismiss(first);
    store.dismiss("missing");
    expect(store.list().map((toast) => toast.title)).toEqual(["Two"]);
  });

  test("keeps at most the limit, dropping the oldest", () => {
    const store = createToastStore({ limit: 3 });
    for (const title of ["a", "b", "c", "d", "e"]) store.push({ tone: "info", title });
    expect(store.list().map((toast) => toast.title)).toEqual(["c", "d", "e"]);
  });

  test("toasts expire after a tone-dependent time; failures stay longer and duration 0 is sticky", () => {
    const clock = manualClock();
    const store = createToastStore({ schedule: clock.schedule });
    store.push({ tone: "success", title: "ok" });
    store.push({ tone: "destructive", title: "failed" });
    store.push({ tone: "info", title: "pinned", duration: 0 });
    expect(clock.pending()).toEqual([4000, 8000]);
    clock.fireAll();
    expect(store.list().map((toast) => toast.title)).toEqual(["pinned"]);
  });

  test("dismissing a toast cancels its timer", () => {
    const clock = manualClock();
    const store = createToastStore({ schedule: clock.schedule });
    const id = store.push({ tone: "info", title: "x" });
    store.dismiss(id);
    expect(clock.pending()).toEqual([]);
  });
});