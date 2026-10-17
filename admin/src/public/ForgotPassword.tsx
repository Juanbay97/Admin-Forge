import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { defaultTheme } from "../brand/theme";
import { issue } from "../i18n/config";
import { cn } from "../lib/cn";
import { z } from "../lib/zod";
import { Alert } from "../ui/Alert";
import { Button, buttonVariants } from "../ui/Button";
import { Field } from "../ui/Field";
import { useZodForm } from "../ui/form";
import { Input } from "../ui/Input";
import { PublicFrame } from "./PublicFrame";

const schema = z.object({
  email: z.string().min(1, issue("public:validation.emailRequired")).pipe(z.email(issue("public:validation.emailInvalid"))),
});

/**
 * Public "forgot password" page for any account (company member, company administrator or platform owner). It asks for the address
 * and always ends on the same neutral confirmation: a failure, an unknown address and a throttled one are indistinguishable.
 */
export function ForgotPassword({ request }: { request: (email: string) => Promise<void> }) {
  const { t } = useTranslation("public");
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
      {t("forgot.backToSignIn")}
    </Link>
  );

  if (sent) {
    return (
      <PublicFrame brand={defaultTheme} title={t("forgot.sentTitle")} description={t("forgot.sentDescription")}>
        <Alert tone="success">{t("forgot.confirmation")}</Alert>
        {back}
      </PublicFrame>
    );
  }
  return (
    <PublicFrame brand={defaultTheme} title={t("forgot.title")} description={t("forgot.description")}>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <Field label={t("forgot.email")} error={errors.email?.message}>
          {(control) => <Input type="email" autoComplete="username" autoFocus {...control} {...form.register("email")} />}
        </Field>
        <Button type="submit" size="lg" loading={isSubmitting}>
          {t("forgot.submit")}
        </Button>
      </form>
      {back}
    </PublicFrame>
  );
}
