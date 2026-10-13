import { useMemo } from "react";
import { qrFor } from "../../platform/qr";

const QUIET = 4;

/** The QR as one SVG path: no `<style>`, no data URI, no script; always black on white so any authenticator can read it. */
export function QrCode({ value, label, className }: { value: string; label: string; className?: string }) {
  const { size, path } = useMemo(() => qrFor(value), [value]);
  const box = size + QUIET * 2;
  return (
    <svg role="img" aria-label={label} viewBox={`${-QUIET} ${-QUIET} ${box} ${box}`} shapeRendering="crispEdges" className={className ?? "size-56 rounded-card border border-line bg-white"}>
      <rect x={-QUIET} y={-QUIET} width={box} height={box} className="fill-white" />
      <path d={path} className="fill-black" />
    </svg>
  );
}
