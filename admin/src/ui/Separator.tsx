import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export function Separator({ className, ...props }: ComponentProps<"hr">) {
  return <hr className={cn("h-px border-0 bg-line", className)} {...props} />;
}