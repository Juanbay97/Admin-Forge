import { Lock } from "lucide-react";
import { Field } from "./Field";
import { Input } from "./Input";

interface KeyFieldProps {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  /** The last four characters the server confirms it holds, when it reports them. */
  lastFour?: string;
  hint?: string;
  error?: string;
  required?: boolean;
}

/**
 * A write-only secret: it is typed here, submitted, and cleared by the caller; it is never read back or displayed.
 * Browsers are told not to remember or autofill it.
 */
export function KeyField({ label, value, onValueChange, lastFour, hint, error, required }: KeyFieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <Field label={label} hint={hint ?? "Write-only: it is never shown again once saved."} error={error} required={required}>
        {(control) => (
          <Input
            type="password"
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="off"
            required={required}
            value={value}
            onChange={(event) => onValueChange(event.target.value)}
            placeholder={lastFour ? "Enter a new key to replace it" : undefined}
            {...control}
          />
        )}
      </Field>
      {lastFour && (
        <p className="flex items-center gap-1.5 text-caption text-muted">
          <Lock aria-hidden="true" className="size-3.5" />
          Saved key ending in {lastFour}
        </p>
      )}
    </div>
  );
}