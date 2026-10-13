import { AlertCircle } from "lucide-react";
import { useId, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { Label } from "./Label";

/** What a control needs to be bound to its label, hint and error. */
export interface FieldControl {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
  "aria-required"?: true;
}

interface FieldProps {
  label: string;
  hint?: string;
  /** The message to show; its presence marks the control invalid. */
  error?: string;
  required?: boolean;
  className?: string;
  children: (control: FieldControl) => ReactNode;
}

/**
 * Label, hint and error bound to one control. The error sits in a polite live region that is always mounted,
 * so a message that appears later is announced; the control points at it through aria-describedby.
 */
export function Field({ label, hint, error, required, className, children }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  const control: FieldControl = {
    id,
    ...(describedBy ? { "aria-describedby": describedBy } : {}),
    ...(error ? { "aria-invalid": true as const } : {}),
    ...(required ? { "aria-required": true as const } : {}),
  };
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required && <span aria-hidden="true" className="ml-0.5 text-danger">*</span>}
      </Label>
      {children(control)}
      {hint && <p id={hintId} className="text-caption text-muted">{hint}</p>}
      <p id={errorId} aria-live="polite" className={cn("flex items-start gap-1.5 text-caption font-medium text-danger", !error && "hidden")}>
        {error && (
          <>
            <AlertCircle aria-hidden="true" className="mt-px size-3.5 shrink-0" />
            <span>{error}</span>
          </>
        )}
      </p>
    </div>
  );
}