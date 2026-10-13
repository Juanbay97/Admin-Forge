import { Loader2 } from "lucide-react";
import { cn } from "../lib/cn";

/** Decorative by default (the surrounding control announces the busy state); pass a label to expose it as a status. */
export function Spinner({ label, className }: { label?: string; className?: string }) {
  const icon = <Loader2 aria-hidden="true" className={cn("size-4 animate-spin", className)} />;
  if (!label) return icon;
  return (
    <span role="status" className="inline-flex items-center gap-2 text-body text-muted">
      {icon}
      {label}
    </span>
  );
}