import { useEffect, useState } from "react";
import type { AccountApi, Department, Organization } from "../api/account";
import { ApiError } from "../api/client";
import type { InviteInput, Member, MembersApi } from "../api/members";
import { InviteDialog } from "../components/InviteDialog";
import { MemberTable } from "../components/MemberTable";
import { NotFound } from "../components/NotFound";
import { applyUpdate, describeFailure, visiblePending, type PendingInvite } from "../members/model";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { PageHeader } from "../ui/PageHeader";
import { AlertDialog } from "../ui/overlay/Dialog";

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
  const [suspending, setSuspending] = useState<Member | null>(null);

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
    <section className="flex flex-col gap-6">
      <PageHeader
        title="Members"
        description="Who can use Forge in your company."
        actions={
          <Button disabled={!ready || ready.departments.length === 0} onClick={() => setInviting(true)}>
            Invite member
          </Button>
        }
      />
      {notice && <Alert tone="success">{notice}</Alert>}
      {failure && <Alert tone="destructive">{failure}</Alert>}
      {load.status === "error" && <Alert tone="destructive">{describeFailure(null, "load")}</Alert>}
      {load.status !== "error" && (
        <MemberTable
          loading={load.status === "loading"}
          members={ready?.members ?? []}
          pending={ready ? visiblePending(pending, ready.members) : []}
          busyId={busyId}
          onChange={(member, action) => (action === "suspend" ? setSuspending(member) : void change(member, action))}
          onInvite={() => setInviting(true)}
        />
      )}
      <InviteDialog open={inviting} departments={ready?.departments ?? []} onSubmit={invite} onClose={() => setInviting(false)} />
      <AlertDialog
        open={suspending !== null}
        onOpenChange={(open) => !open && setSuspending(null)}
        title={`Suspend ${suspending?.display_name ?? ""}?`}
        description="They lose access to Forge until you reactivate them."
        confirmLabel="Suspend"
        destructive
        onConfirm={() => (suspending ? change(suspending, "suspend") : undefined)}
      />
    </section>
  );
}