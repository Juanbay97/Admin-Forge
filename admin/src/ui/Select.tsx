import { ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";
import { controlClasses } from "./Input";

/** The native <select> (it needs no injected styles and keeps platform keyboard and mobile behaviour), styled. */
export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <span className="relative block">
      <select className={cn(controlClasses, "h-10 appearance-none pr-9", className)} {...props}>
        {children}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
    </span>
  );
}