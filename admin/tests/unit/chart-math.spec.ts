import { expect, test } from "@playwright/test";
import { buildAreaPath, buildLinePath } from "../../src/charts/path";
import { linearScale } from "../../src/charts/scale";
import { niceTicks, timeTicks } from "../../src/charts/ticks";

test.describe("niceTicks", () => {
  test("rounds the extent out to 1/2/5 steps", () => {
    expect(niceTicks(0, 97, 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(0, 1, 4)).toEqual([0, 0.5, 1]);
    expect(niceTicks(3, 47, 4)).toEqual([0, 20, 40, 60]);
  });
  test("a flat series still gets a usable axis", () => {
    expect(niceTicks(5, 5, 5)).toEqual([0, 2, 4, 6, 8, 10]);
    expect(niceTicks(0, 0, 5)).toEqual([0, 1]);
  });
  test("NaN and infinite input never throw", () => {
    expect(niceTicks(Number.NaN, 10, 5)).toEqual([0, 1]);
    expect(niceTicks(0, Number.POSITIVE_INFINITY, 5)).toEqual([0, 1]);
  });
});

test.describe("linearScale", () => {
  test("maps the domain onto the range, including inverted ranges for SVG y", () => {
    expect(linearScale([0, 100], [0, 200])(25)).toBe(50);
    expect(linearScale([0, 100], [200, 0])(25)).toBe(150);
  });
  test("clamps when asked and maps a flat domain to the middle of the range", () => {
    expect(linearScale([0, 10], [0, 100], { clamp: true })(15)).toBe(100);
    expect(linearScale([0, 10], [0, 100])(15)).toBe(150);
    expect(linearScale([4, 4], [0, 100])(4)).toBe(50);
    expect(linearScale([0, 10], [0, 100])(Number.NaN)).toBe(0);
  });
});

test.describe("timeTicks", () => {
  const day = (d: number) => Date.UTC(2026, 9, d);
  test("picks whole-day steps that fit the tick budget and labels them in UTC", () => {
    const ticks = timeTicks(day(1), day(30), 6);
    expect(ticks.map((tick) => tick.label)).toEqual(["Oct 1", "Oct 6", "Oct 11", "Oct 16", "Oct 21", "Oct 26"]);
    expect(ticks.every((tick) => tick.t >= day(1) && tick.t <= day(30))).toBe(true);
  });
  test("a week fits one tick per day and a single instant yields one tick", () => {
    expect(timeTicks(day(1), day(7), 8).map((tick) => tick.label)).toEqual(["Oct 1", "Oct 2", "Oct 3", "Oct 4", "Oct 5", "Oct 6", "Oct 7"]);
    expect(timeTicks(day(3), day(3), 6).map((tick) => tick.label)).toEqual(["Oct 3"]);
  });
});

test.describe("paths", () => {
  test("buildLinePath joins points and starts a new segment after a gap", () => {
    expect(buildLinePath([[0, 10], [10.123, 20], [20, 5]])).toBe("M0 10L10.12 20L20 5");
    expect(buildLinePath([[0, 1], null, [2, 3], [3, 4]])).toBe("M0 1M2 3L3 4");
    expect(buildLinePath([[0, 1], [Number.NaN, 2], [4, 5]])).toBe("M0 1M4 5");
    expect(buildLinePath([])).toBe("");
  });
  test("buildAreaPath closes down to the baseline", () => {
    expect(buildAreaPath([[0, 10], [10, 20]], 100)).toBe("M0 10L10 20L10 100L0 100Z");
    expect(buildAreaPath([], 100)).toBe("");
  });
});