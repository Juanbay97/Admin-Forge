import { AlertCircle } from "lucide-react";
import { cn } from "../lib/cn";

/** A form-level failure (a refused sign-in, a conflict); one assertive alert so it is read when it appears. */
export function FormError({ message, className }: { message?: string | null; className?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className={cn("flex items-start gap-2 rounded-control bg-danger-soft px-3 py-2 text-body font-medium text-on-danger-soft", className)}>
      <AlertCircle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </p>
  );
}