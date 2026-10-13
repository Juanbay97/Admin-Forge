// The kit gallery is mounted by `main.tsx` only in the UI-test build (`VITE_KIT=1`) and only for `?kit=<name>`.
import { CoreGallery } from "./CoreGallery";
import { OverlayGallery } from "./OverlayGallery";
import { PrimitiveSpike } from "./PrimitiveSpike";

export function Gallery({ name }: { name: string }) {
  if (name === "primitives") return <PrimitiveSpike />;
  if (name === "core") return <CoreGallery />;
  if (name === "overlays") return <OverlayGallery />;
  return <p role="alert">Unknown kit page.</p>;
}
