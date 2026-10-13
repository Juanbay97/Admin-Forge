import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, CheckCircle2, Info, XCircle, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

const alert = cva("flex gap-3 rounded-card border p-4 text-body", {
  variants: {
    tone: {
      info: "border-line bg-action-soft text-on-action-soft",
      success: "border-line bg-ok-soft text-on-ok-soft",
      warning: "border-line bg-warn-soft text-on-warn-soft",
      destructive: "border-line bg-danger-soft text-on-danger-soft",
    },
  },
  defaultVariants: { tone: "info" },
});

const ICONS: Record<string, LucideIcon> = { info: Info, success: CheckCircle2, warning: AlertTriangle, destructive: XCircle };

interface AlertProps extends VariantProps<typeof alert> {
  title?: string;
  children?: ReactNode;
  /** A retry or follow-up control, placed after the message. */
  action?: ReactNode;
  className?: string;
}

/** Failures and warnings are announced assertively (role=alert); information and success politely (role=status). */
export function Alert({ tone = "info", title, children, action, className }: AlertProps) {
  const Icon = ICONS[tone ?? "info"]!;
  const urgent = tone === "destructive" || tone === "warning";
  return (
    <div role={urgent ? "alert" : "status"} className={cn(alert({ tone }), className)}>
      <Icon aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div>{children}</div>}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  );
}