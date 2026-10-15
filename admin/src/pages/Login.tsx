import { useState } from "react";
import { Link } from "react-router";
import type { AccountApi } from "../api/account";
import { cn } from "../lib/cn";
import { ApiError } from "../api/client";
import { defaultTheme } from "../brand/theme";
import { z } from "../lib/zod";
import { Alert } from "../ui/Alert";
import { Button, buttonVariants } from "../ui/Button";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";
import { useZodForm } from "../ui/form";
import { FormError } from "../ui/FormError";
import { Input } from "../ui/Input";

const MESSAGES: Record<number, string> = {
  401: "Email or password is incorrect.",
  // The server refuses a password under its minimum length with 422 before looking the account up; sign-in must not reveal that rule.
  422: "Email or password is incorrect.",
  429: "Too many sign-in attempts. Try again later.",
};

const schema = z.object({
  email: z.string().min(1, "Enter your email address.").pipe(z.email("Enter a valid email address.")),
  password: z.string().min(1, "Enter your password."),
});

interface LoginProps {
  api: AccountApi;
  onSignedIn: (token: string, email: string) => void;
  /** Why the user is signing in again (an expired session), shown above the form. */
  notice?: string;
}

export function Login({ api, onSignedIn, notice }: LoginProps) {
  const form = useZodForm(schema, { defaultValues: { email: "", password: "" } });
  const [error, setError] = useState<string | null>(null);
  const { errors, isSubmitting } = form.formState;

  const submit = form.handleSubmit(async ({ email, password }) => {
    setError(null);
    form.setValue("password", ""); // the secret never outlives the submit, successful or not
    try {
      onSignedIn(await api.login(email, password), email);
    } catch (failure) {
      const status = failure instanceof ApiError ? failure.status : 0;
      setError(MESSAGES[status] ?? "Sign-in is unavailable. Try again later.");
    }
  });

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-4 sm:p-6">
      <header className="flex items-center gap-4">
        <img src={defaultTheme.assets.markOnLight} alt="" className="h-14 w-auto" />
        <div>
          <h1 className="font-title text-page font-bold text-fg">{defaultTheme.name}</h1>
          <p className="text-body text-muted">Administration</p>
        </div>
      </header>
      {notice && <Alert tone="info">{notice}</Alert>}
      <Card>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4 p-5 sm:p-6">
          <Field label="Email" error={errors.email?.message}>
            {(control) => <Input type="email" autoComplete="username" autoFocus {...control} {...form.register("email")} />}
          </Field>
          <Field label="Password" error={errors.password?.message}>
            {(control) => <Input type="password" autoComplete="current-password" {...control} {...form.register("password")} />}
          </Field>
          <FormError message={error} />
          <Button type="submit" size="lg" loading={isSubmitting}>
            Sign in
          </Button>
          <Link to="/forgot-password" className={cn(buttonVariants({ variant: "link" }), "self-center")}>
            Forgot password?
          </Link>
        </form>
      </Card>
    </main>
  );
}