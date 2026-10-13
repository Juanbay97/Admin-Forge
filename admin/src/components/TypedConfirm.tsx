import { useState } from "react";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { Input } from "../ui/Input";
import { Dialog } from "../ui/overlay/Dialog";

interface TypedConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** What will happen, in plain words. */
  effect: string;
  /** The exact text the person must type before the action is enabled. */
  phrase: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
  /** A refusal from the server, shown inside the dialog. */
  error?: string | null;
}

/** For the actions that cannot be taken back lightly: the confirm button stays disabled until the exact phrase is typed. */
export function TypedConfirm({ open, onOpenChange, title, effect, phrase, confirmLabel, onConfirm, error }: TypedConfirmProps) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const matches = typed === phrase;
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) setTyped(""); onOpenChange(next); }} title={title} role="alertdialog" dismissOnBackdrop={false}>
      <form
        className="flex flex-col gap-4"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!matches || busy) return;
          setBusy(true);
          try {
            await onConfirm();
            setTyped("");
          } finally {
            setBusy(false);
          }
        }}
      >
        <Alert tone="warning">{effect}</Alert>
        <Field label={`Type ${phrase} to confirm`}>
          {(control) => <Input {...control} value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" spellCheck={false} data-autofocus />}
        </Field>
        {error && <Alert tone="destructive">{error}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" variant="destructive" disabled={!matches} loading={busy}>{confirmLabel}</Button>
        </div>
      </form>
    </Dialog>
  );
}