import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Department } from "../api/account";
import type { Member } from "../api/members";
import { describeFailure } from "../members/model";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { FormError } from "../ui/FormError";
import { Select } from "../ui/Select";
import { Dialog } from "../ui/overlay/Dialog";

interface Props {
  /** The member being moved; the dialog is open while this is set. */
  member: Member | null;
  departments: Department[];
  onSubmit: (departmentId: string) => Promise<void>;
  onClose: () => void;
}

/** Mounted only while open (keyed by member), so every assignment starts on the member's current department. */
function AssignForm({ member, departments, onSubmit, onClose }: Props & { member: Member }) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState(member.departments[0]?.id ?? departments[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sorted = [...departments].sort((a, b) => a.name.localeCompare(b.name));

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await onSubmit(choice);
    } catch (failure) {
      setError(describeFailure(failure, "assign"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <Field label={t("members.assign.department")}>
        {(control) => (
          <Select {...control} value={choice} onChange={(event) => setChoice(event.target.value)}>
            {sorted.map((department) => (
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
        <Button type="submit" loading={busy} disabled={!choice}>
          {t("members.assign.submit")}
        </Button>
      </div>
    </form>
  );
}

export function AssignDepartmentDialog({ member, departments, onSubmit, onClose }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={member !== null}
      onOpenChange={(next) => !next && onClose()}
      title={t("members.assign.title")}
      description={member ? t("members.assign.description", { name: member.display_name }) : undefined}
    >
      {member && <AssignForm key={member.id} member={member} departments={departments} onSubmit={onSubmit} onClose={onClose} />}
    </Dialog>
  );
}
