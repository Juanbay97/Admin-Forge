import { X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { cn } from "../../lib/cn";
import { Button } from "../Button";

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children?: ReactNode;
  role?: "dialog" | "alertdialog";
  /** `right` makes a full-height Sheet. */
  side?: "center" | "right";
  /** A confirmation must be answered, so a click outside does not dismiss it. */
  dismissOnBackdrop?: boolean;
  className?: string;
}

const FIRST_FIELD = "[data-autofocus], input:not([type=hidden]), select, textarea";

/**
 * Native `<dialog>` opened with showModal(): the browser provides the focus trap, the inert background, Escape and the
 * return of focus to the trigger, with no injected styles. Content is mounted only while open, so forms start fresh.
 */
export function Dialog({ open, onOpenChange, title, description, children, role = "dialog", side = "center", dismissOnBackdrop = true, className }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (open && !element.open) {
      element.showModal();
      element.querySelector<HTMLElement>(FIRST_FIELD)?.focus();
    } else if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      role={role}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onClose={() => onOpenChange(false)}
      onClick={(event) => {
        if (dismissOnBackdrop && event.target === event.currentTarget) onOpenChange(false);
      }}
      className={cn(
        "bg-surface p-0 text-fg shadow-overlay backdrop:bg-nav/60",
        side === "right"
          ? "m-0 ml-auto h-dvh max-h-none w-full max-w-md rounded-none border-l border-line"
          : "m-auto w-[calc(100%-2rem)] max-w-md rounded-card border border-line",
        className,
      )}
    >
      {open && (
        <div className={cn("flex flex-col gap-4 p-6", side === "right" && "h-full overflow-y-auto")}>
          <header className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <h2 id={titleId} className="font-title text-section font-semibold">{title}</h2>
              {description && <p id={descriptionId} className="text-body text-muted">{description}</p>}
            </div>
            {role === "dialog" && (
              <Button variant="ghost" size="icon" aria-label="Close" onClick={() => onOpenChange(false)} className="-mr-2 -mt-2">
                <X aria-hidden="true" className="size-5" />
              </Button>
            )}
          </header>
          {children}
        </div>
      )}
    </dialog>
  );
}

export function Sheet(props: Omit<DialogProps, "side" | "role">) {
  return <Dialog {...props} side="right" />;
}

interface AlertDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
}

/** For destructive or irreversible actions: it starts on the safe choice and is only closed by an explicit answer or Escape. */
export function AlertDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", cancelLabel = "Cancel", destructive = false, onConfirm }: AlertDialogProps) {
  const [busy, setBusy] = useState(false);
  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} description={description} role="alertdialog" dismissOnBackdrop={false}>
      <div className="flex justify-end gap-3">
        <Button variant="outline" data-autofocus onClick={() => onOpenChange(false)}>{cancelLabel}</Button>
        <Button variant={destructive ? "destructive" : "default"} loading={busy} onClick={() => void confirm()}>{confirmLabel}</Button>
      </div>
    </Dialog>
  );
}