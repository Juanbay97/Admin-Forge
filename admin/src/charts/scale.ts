export interface ScaleOptions {
  clamp?: boolean;
}

/** Maps a numeric domain onto a range (the range may be inverted, as SVG y is). A flat domain maps to the middle. */
export function linearScale(domain: readonly [number, number], range: readonly [number, number], { clamp = false }: ScaleOptions = {}) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  return (value: number): number => {
    if (!Number.isFinite(value)) return r0;
    if (d0 === d1) return (r0 + r1) / 2;
    const ratio = (value - d0) / (d1 - d0);
    const bounded = clamp ? Math.min(1, Math.max(0, ratio)) : ratio;
    return r0 + bounded * (r1 - r0);
  };
}