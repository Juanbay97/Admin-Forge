export interface Assigned {
  key_id: string;
  priority: number;
  active: boolean;
}

/** List order is priority order: the first key is tried first. */
export const toEntries = (list: ReadonlyArray<{ key_id: string; active: boolean }>): Assigned[] =>
  list.map((item, index) => ({ key_id: item.key_id, priority: index + 1, active: item.active }));

export function move<T extends { key_id: string }>(list: readonly T[], id: string, by: -1 | 1): T[] {
  const from = list.findIndex((item) => item.key_id === id);
  const to = from + by;
  if (from < 0 || to < 0 || to >= list.length) return [...list];
  const copy = [...list];
  [copy[from], copy[to]] = [copy[to]!, copy[from]!];
  return copy;
}

export const addKey = (list: readonly Assigned[], id: string): Assigned[] =>
  list.some((item) => item.key_id === id) ? [...list] : toEntries([...list, { key_id: id, active: true }]);

export const removeKey = (list: readonly Assigned[], id: string): Assigned[] => toEntries(list.filter((item) => item.key_id !== id));

export const usableCount = (list: readonly Assigned[]): number => list.filter((item) => item.active).length;