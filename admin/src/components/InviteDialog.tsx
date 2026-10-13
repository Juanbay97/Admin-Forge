import { useState } from "react";
import type { Department } from "../api/account";
import type { InviteInput } from "../api/members";
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
  name: z.string().trim().min(1, "Enter the member's name.").max(120, "Use at most 120 characters."),
  email: z.string().min(1, "Enter the member's email address.").pipe(z.email("Enter a valid email address.")),
  departmentId: z.string().min(1, "Choose a department."),
});

/** The form lives inside the dialog, which mounts it only while open, so every invitation starts from a clean form. */
function InviteForm({ departments, onSubmit, onClose }: Omit<InviteDialogProps, "open">) {
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
      <Field label="Name" error={errors.name?.message}>
        {(control) => <Input maxLength={120} autoComplete="off" {...control} {...form.register("name")} />}
      </Field>
      <Field label="Email" error={errors.email?.message}>
        {(control) => <Input type="email" autoComplete="off" {...control} {...form.register("email")} />}
      </Field>
      <Field label="Department" error={errors.departmentId?.message}>
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
          Cancel
        </Button>
        <Button type="submit" loading={isSubmitting}>
          Send invitation
        </Button>
      </div>
    </form>
  );
}

export function InviteDialog({ open, departments, onSubmit, onClose }: InviteDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()} title="Invite a member" description="They receive an email with a link to activate their account.">
      <InviteForm departments={departments} onSubmit={onSubmit} onClose={onClose} />
    </Dialog>
  );
}