import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, CheckCircle2, CircleSlash, Info, type LucideIcon } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

const badge = cva("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-caption font-medium", {
  variants: {
    tone: {
      neutral: "bg-subtle text-fg ring-1 ring-inset ring-line",
      info: "bg-action-soft text-on-action-soft",
      success: "bg-ok-soft text-on-ok-soft",
      warning: "bg-warn-soft text-on-warn-soft",
      destructive: "bg-danger-soft text-on-danger-soft",
    },
  },
  defaultVariants: { tone: "neutral" },
});

const ICONS: Record<string, LucideIcon> = { neutral: CircleSlash, info: Info, success: CheckCircle2, warning: AlertTriangle, destructive: AlertTriangle };

/** Status is never colour alone: every badge carries an icon next to its text. */
export function Badge({ tone = "neutral", className, children, ...props }: ComponentProps<"span"> & VariantProps<typeof badge>) {
  const Icon = ICONS[tone ?? "neutral"]!;
  return (
    <span className={cn(badge({ tone }), className)} {...props}>
      <Icon aria-hidden="true" className="size-3" />
      {children}
    </span>
  );
}