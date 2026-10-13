// Pure sorting and paging rules of DataTable.
export type Direction = "asc" | "desc";
export interface Sort {
  id: string;
  direction: Direction;
}

const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });
type Key = string | number | null | undefined;

const missing = (key: Key): key is null | undefined => key === null || key === undefined || (typeof key === "number" && Number.isNaN(key));

/** Stable; text compares case-insensitively, numbers numerically, and missing values stay last in both directions. */
export function sortRows<T>(rows: readonly T[], keyOf: (row: T) => Key, direction: Direction): T[] {
  const sign = direction === "asc" ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, key: keyOf(row) }))
    .sort((a, b) => {
      if (missing(a.key) || missing(b.key)) return missing(a.key) === missing(b.key) ? a.index - b.index : missing(a.key) ? 1 : -1;
      const order = typeof a.key === "number" && typeof b.key === "number" ? a.key - b.key : collator.compare(String(a.key), String(b.key));
      return order === 0 ? a.index - b.index : sign * order;
    })
    .map((entry) => entry.row);
}

/** Ascending, then descending, then unsorted; a different column starts ascending. */
export function nextSort(current: Sort | null, id: string): Sort | null {
  if (current?.id !== id) return { id, direction: "asc" };
  return current.direction === "asc" ? { id, direction: "desc" } : null;
}

export function paginate<T>(items: readonly T[], page: number, size: number) {
  const pageCount = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(1, page), pageCount);
  return { items: items.slice((current - 1) * size, current * size), page: current, pageCount, total: items.length };
}