import { Building2 } from "lucide-react";
import { useState } from "react";
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
      setFailure(error instanceof ApiError && error.status === 409 ? "A department with that name already exists." : "The department could not be created. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex max-w-xl flex-col gap-6">
      {sorted.length === 0 ? (
        <EmptyState icon={Building2} title="No departments yet" hint="Departments group your people; members are invited into one." />
      ) : (
        <ul aria-label="Departments" className="grid gap-2 sm:grid-cols-2">
          {sorted.map((department) => (
            <li key={department.id} className="flex min-h-11 items-center gap-3 rounded-control border border-line bg-subtle px-3 text-body">
              <Building2 aria-hidden="true" className="size-4 shrink-0 text-muted" />
              {department.name}
            </li>
          ))}
        </ul>
      )}
      <form noValidate className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <Field label="New department">{(control) => <Input {...control} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" maxLength={120} />}</Field>
        {failure && <Alert tone="destructive">{failure}</Alert>}
        <div><Button type="submit" loading={busy} disabled={!name.trim()}>Create department</Button></div>
      </form>
    </div>
  );
}