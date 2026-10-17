import { Building2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Department } from "../api/account";
import { ApiError } from "../api/client";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Field } from "../ui/Field";
import { Input } from "../ui/Input";

interface Props {
  departments: Department[];
  onCreate: (name: string) => Promise<void>;
}

/** The company's departments, alphabetical, and a one-field form to add another. Renaming and removing are not offered by the API. */
export function DepartmentsPanel({ departments, onCreate }: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const sorted = [...departments].sort((a, b) => a.name.localeCompare(b.name));

  async function submit() {
    const clean = name.trim();
    if (!clean) return;
    setBusy(true);
    setFailure(null);
    try {
      await onCreate(clean);
      setName("");
    } catch (error) {
      setFailure(error instanceof ApiError && error.status === 409 ? t("members.departments.exists") : t("members.departments.createFailed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex max-w-xl flex-col gap-6">
      {sorted.length === 0 ? (
        <EmptyState icon={Building2} title={t("members.departments.emptyTitle")} hint={t("members.departments.emptyHint")} />
      ) : (
        <ul aria-label={t("members.departments.list")} className="grid gap-2 sm:grid-cols-2">
          {sorted.map((department) => (
            <li key={department.id} className="flex min-h-11 items-center gap-3 rounded-control border border-line bg-subtle px-3 text-body">
              <Building2 aria-hidden="true" className="size-4 shrink-0 text-muted" />
              {department.name}
            </li>
          ))}
        </ul>
      )}
      <form noValidate className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <Field label={t("members.departments.newDepartment")}>{(control) => <Input {...control} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" maxLength={120} />}</Field>
        {failure && <Alert tone="destructive">{failure}</Alert>}
        <div><Button type="submit" loading={busy} disabled={!name.trim()}>{t("members.departments.create")}</Button></div>
      </form>
    </div>
  );
}