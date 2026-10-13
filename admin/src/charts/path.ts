export type Point = readonly [number, number];

const round = (value: number): string => String(Math.round(value * 100) / 100);
const valid = (point: Point | null): point is Point => point !== null && Number.isFinite(point[0]) && Number.isFinite(point[1]);

/** An SVG path through the points; a null or non-finite point is a gap and the next valid point starts a new segment. */
export function buildLinePath(points: ReadonlyArray<Point | null>): string {
  let path = "";
  let open = false;
  for (const point of points) {
    if (!valid(point)) {
      open = false;
      continue;
    }
    path += `${open ? "L" : "M"}${round(point[0])} ${round(point[1])}`;
    open = true;
  }
  return path;
}

/** The same line closed down to `baseline` (an SVG y) for an area fill; gaps are skipped. */
export function buildAreaPath(points: ReadonlyArray<Point | null>, baseline: number): string {
  const usable = points.filter(valid);
  const first = usable[0];
  const last = usable[usable.length - 1];
  if (!first || !last) return "";
  return `${buildLinePath(usable)}L${round(last[0])} ${round(baseline)}L${round(first[0])} ${round(baseline)}Z`;
}