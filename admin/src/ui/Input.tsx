import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export const controlClasses =
  "w-full rounded-control border border-line-strong bg-surface px-3 text-body text-fg placeholder:text-muted " +
  "outline-focus focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:border-focus " +
  "disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger max-sm:min-h-11";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return <input type={type} className={cn(controlClasses, "h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(controlClasses, "min-h-24 py-2", className)} {...props} />;
}