import { expect, test } from "@playwright/test";
import { nextSort, paginate, sortRows } from "../../src/ui/table";

const rows = [
  { name: "Cy", tokens: 30 },
  { name: "alex", tokens: 120 },
  { name: "Bea", tokens: 9 },
  { name: "Dee", tokens: null as number | null },
];

test.describe("sortRows", () => {
  test("sorts text case-insensitively and does not mutate its input", () => {
    const before = rows.map((row) => row.name);
    expect(sortRows(rows, (row) => row.name, "asc").map((row) => row.name)).toEqual(["alex", "Bea", "Cy", "Dee"]);
    expect(sortRows(rows, (row) => row.name, "desc").map((row) => row.name)).toEqual(["Dee", "Cy", "Bea", "alex"]);
    expect(rows.map((row) => row.name)).toEqual(before);
  });

  test("sorts numbers numerically and keeps missing values last in both directions", () => {
    expect(sortRows(rows, (row) => row.tokens, "asc").map((row) => row.name)).toEqual(["Bea", "Cy", "alex", "Dee"]);
    expect(sortRows(rows, (row) => row.tokens, "desc").map((row) => row.name)).toEqual(["alex", "Cy", "Bea", "Dee"]);
  });

  test("is stable for equal keys", () => {
    const tied = [{ id: 1, k: "x" }, { id: 2, k: "x" }, { id: 3, k: "x" }];
    expect(sortRows(tied, (row) => row.k, "desc").map((row) => row.id)).toEqual([1, 2, 3]);
  });
});

test.describe("nextSort", () => {
  test("a column cycles ascending, descending, then unsorted; another column starts ascending", () => {
    expect(nextSort(null, "name")).toEqual({ id: "name", direction: "asc" });
    expect(nextSort({ id: "name", direction: "asc" }, "name")).toEqual({ id: "name", direction: "desc" });
    expect(nextSort({ id: "name", direction: "desc" }, "name")).toBeNull();
    expect(nextSort({ id: "name", direction: "desc" }, "tokens")).toEqual({ id: "tokens", direction: "asc" });
  });
});

test.describe("paginate", () => {
  const items = Array.from({ length: 12 }, (_, index) => index + 1);
  test("slices a page and reports the page count", () => {
    expect(paginate(items, 2, 5)).toEqual({ items: [6, 7, 8, 9, 10], page: 2, pageCount: 3, total: 12 });
    expect(paginate(items, 3, 5).items).toEqual([11, 12]);
  });
  test("clamps an out-of-range page and handles no rows", () => {
    expect(paginate(items, 9, 5).page).toBe(3);
    expect(paginate(items, 0, 5).page).toBe(1);
    expect(paginate([], 4, 5)).toEqual({ items: [], page: 1, pageCount: 1, total: 0 });
  });
});