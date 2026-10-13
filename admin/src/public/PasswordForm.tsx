import { Check, Circle, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { z } from "../lib/zod";
import { MIN_PASSWORD } from "./passwordRules";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { useZodForm } from "../ui/form";
import { FormError } from "../ui/FormError";
import { Input } from "../ui/Input";

export { MIN_PASSWORD };

export const passwordSchema = z
  .object({ password: z.string().min(MIN_PASSWORD, `Use at least ${MIN_PASSWORD} characters.`).max(1024, "That password is too long."), confirm: z.string() })
  .refine((value) => value.password === value.confirm, { path: ["confirm"], message: "The passwords do not match." });

interface Props {
  submitLabel: string;
  onSubmit: (password: string) => Promise<void>;
  error?: string | null;
  /** Extra fields rendered above the password (the join page asks for the email once). */
  children?: React.ReactNode;
}

/** Password + confirmation with a live length hint, a show/hide toggle and a single guarded submit; the value never outlives it. */
export function PasswordForm({ submitLabel, onSubmit, error, children }: Props) {
  const form = useZodForm(passwordSchema, { defaultValues: { password: "", confirm: "" } });
  const [shown, setShown] = useState(false);
  const { errors, isSubmitting } = form.formState;
  const long = form.watch("password").length >= MIN_PASSWORD;
  const submit = form.handleSubmit(async ({ password }) => {
    try {
      await onSubmit(password);
    } finally {
      form.reset({ password: "", confirm: "" });
    }
  });
  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      {children}
      <Field label="New password" error={errors.password?.message}>
        {(control) => (
          <div className="flex gap-2">
            <Input type={shown ? "text" : "password"} autoComplete="new-password" autoFocus {...control} {...form.register("password")} />
            <Button variant="outline" size="icon" aria-label={shown ? "Hide password" : "Show password"} aria-pressed={shown} onClick={() => setShown((value) => !value)}>
              {shown ? <EyeOff aria-hidden="true" className="size-4" /> : <Eye aria-hidden="true" className="size-4" />}
            </Button>
          </div>
        )}
      </Field>
      <p className="flex items-center gap-2 text-caption text-muted" data-met={long}>
        {long ? <Check aria-hidden="true" className="size-4 text-on-ok-soft" /> : <Circle aria-hidden="true" className="size-4" />}
        <span>At least {MIN_PASSWORD} characters{long ? " ✓" : ""}</span>
      </p>
      <Field label="Confirm password" error={errors.confirm?.message}>
        {(control) => <Input type={shown ? "text" : "password"} autoComplete="new-password" {...control} {...form.register("confirm")} />}
      </Field>
      <FormError message={error ?? null} />
      <Button type="submit" size="lg" loading={isSubmitting}>
        {submitLabel}
      </Button>
    </form>
  );
}
