import { expect, test } from "@playwright/test";
import { addKey, move, removeKey, toEntries, usableCount } from "../../src/platform/assignments";

const rows = [
  { key_id: "a", priority: 1, active: true },
  { key_id: "b", priority: 2, active: false },
  { key_id: "c", priority: 3, active: true },
];

test.describe("key assignment list", () => {
  test("entries are numbered 1..n in list order", () => {
    expect(toEntries([{ key_id: "x", active: true }, { key_id: "y", active: false }])).toEqual([{ key_id: "x", priority: 1, active: true }, { key_id: "y", priority: 2, active: false }]);
  });
  test("moving a key swaps it with its neighbour and stops at the ends", () => {
    expect(move(rows, "c", -1).map((row) => row.key_id)).toEqual(["a", "c", "b"]);
    expect(move(rows, "a", 1).map((row) => row.key_id)).toEqual(["b", "a", "c"]);
    expect(move(rows, "a", -1).map((row) => row.key_id)).toEqual(["a", "b", "c"]);
    expect(move(rows, "c", 1).map((row) => row.key_id)).toEqual(["a", "b", "c"]);
    expect(move(rows, "zzz", 1)).toEqual(rows);
  });
  test("adding appends once; removing drops it", () => {
    expect(addKey(rows, "d").map((row) => row.key_id)).toEqual(["a", "b", "c", "d"]);
    expect(addKey(rows, "a")).toHaveLength(3);
    expect(removeKey(rows, "b").map((row) => row.key_id)).toEqual(["a", "c"]);
  });
  test("a company works while at least one assigned key is active", () => {
    expect(usableCount(rows)).toBe(2);
    expect(usableCount([{ key_id: "a", priority: 1, active: false }])).toBe(0);
    expect(usableCount([])).toBe(0);
  });
});