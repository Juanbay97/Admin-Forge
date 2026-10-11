import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Department } from "../api/account";
import type { InviteInput } from "../api/members";
import { describeFailure } from "../members/model";

interface InviteDialogProps {
  open: boolean;
  departments: Department[];
  onSubmit: (input: InviteInput) => Promise<void>;
  onClose: () => void;
}

const FIELD = "rounded border border-carbon/40 px-3 py-2 text-base";

export function InviteDialog({ open, departments, onSubmit, onClose }: InviteDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      setName("");
      setEmail("");
      setError(null);
      setDepartmentId(departments[0]?.id ?? "");
      element.showModal(); // native modal: focus trap, Escape and focus return come for free
    } else if (!open && element.open) {
      element.close();
    }
  }, [open, departments]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name, email, departmentId });
    } catch (failure) {
      setError(describeFailure(failure, "invite"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      aria-labelledby="invite-title"
      onClose={onClose}
      className="m-auto w-full max-w-md rounded-lg p-0 shadow-xl backdrop:bg-primary/60"
    >
      <form onSubmit={submit} className="flex flex-col gap-4 p-6">
        <h2 id="invite-title" className="font-title text-lg font-bold text-primary">
          Invite a member
        </h2>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Name
          <input required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Email
          <input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Department
          <select required value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} className={FIELD}>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <p role="alert" className="text-sm font-medium text-red-800">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={() => dialog.current?.close()}
            className="rounded border border-carbon/40 px-4 py-2 transition-colors hover:bg-sand"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-teal px-4 py-2 font-medium text-white transition-colors hover:bg-primary disabled:opacity-60"
          >
            Send invitation
          </button>
        </div>
      </form>
    </dialog>
  );
}