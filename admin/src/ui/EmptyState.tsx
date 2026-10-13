import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

/** Zero items: say what this place is for and offer the one action that fills it. */
export function EmptyState({ icon: Icon, title, hint, action, className }: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-3 rounded-card border border-dashed border-line-strong bg-surface px-6 py-12 text-center", className)}>
      <span className="flex size-12 items-center justify-center rounded-full bg-action-soft text-on-action-soft">
        <Icon aria-hidden="true" className="size-6" />
      </span>
      <h3 className="font-title text-card font-semibold text-fg">{title}</h3>
      {hint && <p className="max-w-sm text-body text-muted">{hint}</p>}
      {action}
    </div>
  );
}