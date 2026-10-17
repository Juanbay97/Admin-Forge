import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Department } from "../api/account";
import type { InviteInput } from "../api/members";
import { issue } from "../i18n/config";
import { z } from "../lib/zod";
import { describeFailure } from "../members/model";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { useZodForm } from "../ui/form";
import { FormError } from "../ui/FormError";
import { Input } from "../ui/Input";
import { Dialog } from "../ui/overlay/Dialog";
import { Select } from "../ui/Select";

interface InviteDialogProps {
  open: boolean;
  departments: Department[];
  onSubmit: (input: InviteInput) => Promise<void>;
  onClose: () => void;
}

const schema = z.object({
  name: z.string().trim().min(1, issue("common:members.invite.nameRequired")).max(120, issue("common:members.invite.nameMax")),
  email: z.string().min(1, issue("common:members.invite.emailRequired")).pipe(z.email(issue("public:validation.emailInvalid"))),
  departmentId: z.string().min(1, issue("common:members.invite.chooseDepartment")),
});

/** The form lives inside the dialog, which mounts it only while open, so every invitation starts from a clean form. */
function InviteForm({ departments, onSubmit, onClose }: Omit<InviteDialogProps, "open">) {
  const { t } = useTranslation();
  const form = useZodForm(schema, { defaultValues: { name: "", email: "", departmentId: departments[0]?.id ?? "" } });
  const [error, setError] = useState<string | null>(null);
  const { errors, isSubmitting } = form.formState;
  const submit = form.handleSubmit(async (input) => {
    setError(null);
    try {
      await onSubmit(input);
    } catch (failure) {
      setError(describeFailure(failure, "invite"));
    }
  });
  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <Field label={t("members.invite.name")} error={errors.name?.message}>
        {(control) => <Input maxLength={120} autoComplete="off" {...control} {...form.register("name")} />}
      </Field>
      <Field label={t("members.invite.email")} error={errors.email?.message}>
        {(control) => <Input type="email" autoComplete="off" {...control} {...form.register("email")} />}
      </Field>
      <Field label={t("members.invite.department")} error={errors.departmentId?.message}>
        {(control) => (
          <Select {...control} {...form.register("departmentId")}>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <FormError message={error} />
      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={onClose}>
          {t("actions.cancel")}
        </Button>
        <Button type="submit" loading={isSubmitting}>
          {t("members.invite.submit")}
        </Button>
      </div>
    </form>
  );
}

export function InviteDialog({ open, departments, onSubmit, onClose }: InviteDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()} title={t("members.invite.title")} description={t("members.invite.description")}>
      <InviteForm departments={departments} onSubmit={onSubmit} onClose={onClose} />
    </Dialog>
  );
}