import { useEffect, useState } from "react";
import type { AccountApi, Department, Organization } from "../api/account";
import { ApiError } from "../api/client";
import type { InviteInput, Member, MembersApi } from "../api/members";
import { InviteDialog } from "../components/InviteDialog";
import { MemberTable } from "../components/MemberTable";
import { NotFound } from "../components/NotFound";
import { applyUpdate, describeFailure, visiblePending, type PendingInvite } from "../members/model";

interface MembersProps {
  api: AccountApi;
  membersApi: MembersApi;
  organization: Organization;
}

type Load =
  | { status: "loading" | "not-found" | "error" }
  | { status: "ready"; members: Member[]; departments: Department[] };

export function Members({ api, membersApi, organization }: MembersProps) {
  const orgId = organization.id;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [pending, setPending] = useState<PendingInvite[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    let current = true;
    Promise.all([membersApi.list(orgId), api.departments(orgId)]).then(
      ([members, departments]) => current && setLoad({ status: "ready", members, departments }),
      (error: unknown) => current && setLoad({ status: error instanceof ApiError && error.status === 404 ? "not-found" : "error" }),
    );
    return () => {
      current = false;
    };
  }, [api, membersApi, orgId]);

  if (load.status === "not-found") return <NotFound />;

  async function change(member: Member, action: "suspend" | "reactivate") {
    setBusyId(member.id);
    setFailure(null);
    setNotice(null);
    try {
      const updated = await membersApi[action](orgId, member.id);
      setLoad((state) => (state.status === "ready" ? { ...state, members: applyUpdate(state.members, updated) } : state));
    } catch (error) {
      setFailure(describeFailure(error, action));
    } finally {
      setBusyId(null);
    }
  }

  async function invite(input: InviteInput) {
    await membersApi.invite(orgId, input);
    const departments = load.status === "ready" ? load.departments : [];
    const departmentName = departments.find((department) => department.id === input.departmentId)?.name ?? "";
    setPending((current) => [...current, { email: input.email, name: input.name, departmentName }]);
    setNotice(`Invitation sent to ${input.email}.`);
    setInviting(false);
  }

  const ready = load.status === "ready" ? load : null;
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-title text-2xl font-bold text-primary">Members</h1>
        <button
          type="button"
          disabled={!ready || ready.departments.length === 0}
          onClick={() => setInviting(true)}
          className="rounded bg-teal px-4 py-2 font-medium text-white transition-colors hover:bg-primary disabled:opacity-60"
        >
          Invite member
        </button>
      </div>
      {notice && <p role="status">{notice}</p>}
      {failure && <p role="alert" className="font-medium text-red-800">{failure}</p>}
      {load.status === "loading" && <p role="status">Loading members…</p>}
      {load.status === "error" && <p role="alert" className="font-medium text-red-800">{describeFailure(null, "load")}</p>}
      {ready && (
        <MemberTable
          members={ready.members}
          pending={visiblePending(pending, ready.members)}
          busyId={busyId}
          onChange={change}
        />
      )}
      <InviteDialog
        open={inviting}
        departments={ready?.departments ?? []}
        onSubmit={invite}
        onClose={() => setInviting(false)}
      />
    </section>
  );
}