// The kit gallery is mounted by `main.tsx` only in the UI-test build (`VITE_KIT=1`) and only for `?kit=<name>`.
import { PrimitiveSpike } from "./PrimitiveSpike";

export function Gallery({ name }: { name: string }) {
  if (name === "primitives") return <PrimitiveSpike />;
  return <p role="alert">Unknown kit page.</p>;
}