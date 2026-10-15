import { useState } from "react";
import { Link } from "react-router";
import { defaultTheme } from "../brand/theme";
import { cn } from "../lib/cn";
import { z } from "../lib/zod";
import { Alert } from "../ui/Alert";
import { Button, buttonVariants } from "../ui/Button";
import { Field } from "../ui/Field";
import { useZodForm } from "../ui/form";
import { Input } from "../ui/Input";
import { PublicFrame } from "./PublicFrame";

export const FORGOT_CONFIRMATION = "If an account exists for that address, we sent a link to set a new password. Check your inbox.";

const schema = z.object({
  email: z.string().min(1, "Enter your email address.").pipe(z.email("Enter a valid email address.")),
});

/**
 * Public "forgot password" page for any account (company member, company administrator or platform owner). It asks for the address
 * and always ends on the same neutral confirmation: a failure, an unknown address and a throttled one are indistinguishable.
 */
export function ForgotPassword({ request }: { request: (email: string) => Promise<void> }) {
  const form = useZodForm(schema, { defaultValues: { email: "" } });
  const [sent, setSent] = useState(false);
  const { errors, isSubmitting } = form.formState;

  const submit = form.handleSubmit(async ({ email }) => {
    try {
      await request(email);
    } catch {
      // Deliberately swallowed: the page must not reveal whether the address is known or the relay is reachable.
    }
    setSent(true);
  });

  const back = (
    <Link to="/" className={cn(buttonVariants({ variant: "link" }), "self-start")}>
      Back to sign in
    </Link>
  );

  if (sent) {
    return (
      <PublicFrame brand={defaultTheme} title="Check your inbox" description="The link is single-use and expires soon.">
        <Alert tone="success">{FORGOT_CONFIRMATION}</Alert>
        {back}
      </PublicFrame>
    );
  }
  return (
    <PublicFrame brand={defaultTheme} title="Forgot your password?" description="Enter the email address of your account and we will send you a link to set a new password.">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <Field label="Email" error={errors.email?.message}>
          {(control) => <Input type="email" autoComplete="username" autoFocus {...control} {...form.register("email")} />}
        </Field>
        <Button type="submit" size="lg" loading={isSubmitting}>
          Send reset link
        </Button>
      </form>
      {back}
    </PublicFrame>
  );
}
