import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

/** A pulsing placeholder with the final size of what it stands for, so content arrives without layout shift. */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-control bg-line", className)} {...props} />;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className={cn("h-4", index === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}