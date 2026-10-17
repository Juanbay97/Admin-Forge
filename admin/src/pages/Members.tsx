import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AccountApi, Department, Organization } from "../api/account";
import { ApiError } from "../api/client";
import type { InviteInput, Member, MembersApi } from "../api/members";
import { AssignDepartmentDialog } from "../components/AssignDepartmentDialog";
import { InviteDialog } from "../components/InviteDialog";
import { MemberTable } from "../components/MemberTable";
import { NotFound } from "../components/NotFound";
import { applyUpdate, describeFailure, visiblePending, type PendingInvite } from "../members/model";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { PageHeader } from "../ui/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/Tabs";
import { DepartmentsPanel } from "../components/DepartmentsPanel";
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
  const { t } = useTranslation(["company", "common"]);
  const orgId = organization.id;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [pending, setPending] = useState<PendingInvite[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [suspending, setSuspending] = useState<Member | null>(null);
  const [assigning, setAssigning] = useState<Member | null>(null);

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

  async function assign(departmentId: string) {
    if (!assigning) return;
    const updated = await membersApi.assignDepartment(orgId, assigning.id, departmentId);
    setLoad((state) => (state.status === "ready" ? { ...state, members: applyUpdate(state.members, updated) } : state));
    setAssigning(null);
  }

  async function invite(input: InviteInput) {
    await membersApi.invite(orgId, input);
    const departments = load.status === "ready" ? load.departments : [];
    const departmentName = departments.find((department) => department.id === input.departmentId)?.name ?? "";
    setPending((current) => [...current, { email: input.email, name: input.name, departmentName }]);
    setNotice(t("members.invitationSent", { email: input.email }));
    setInviting(false);
  }

  const ready = load.status === "ready" ? load : null;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader
        title={t("members.title")}
        description={t("members.description")}
        actions={
          <Button disabled={!ready || ready.departments.length === 0} onClick={() => setInviting(true)}>
            {t("members.invite")}
          </Button>
        }
      />
      {notice && <Alert tone="success">{notice}</Alert>}
      {failure && <Alert tone="destructive">{failure}</Alert>}
      {load.status === "error" && <Alert tone="destructive">{describeFailure(null, "load")}</Alert>}
      {load.status !== "error" && (
        <Tabs defaultValue="people">
          <TabsList aria-label={t("members.sections")}>
            <TabsTrigger value="people">{t("members.people")}</TabsTrigger>
            <TabsTrigger value="departments">{t("members.departments")}</TabsTrigger>
          </TabsList>
          <TabsContent value="people">
            <MemberTable
              loading={load.status === "loading"}
              members={ready?.members ?? []}
              pending={ready ? visiblePending(pending, ready.members) : []}
              busyId={busyId}
              departments={ready?.departments}
              onChange={(member, action) => (action === "suspend" ? setSuspending(member) : void change(member, action))}
              onInvite={() => setInviting(true)}
              onAssign={setAssigning}
            />
          </TabsContent>
          <TabsContent value="departments">
            <DepartmentsPanel
              departments={ready?.departments ?? []}
              onCreate={async (name) => {
                const created = await api.createDepartment(orgId, name);
                setLoad((state) => (state.status === "ready" ? { ...state, departments: [...state.departments, created] } : state));
              }}
            />
          </TabsContent>
        </Tabs>
      )}
      <AssignDepartmentDialog member={assigning} departments={ready?.departments ?? []} onSubmit={assign} onClose={() => setAssigning(null)} />
      <InviteDialog open={inviting} departments={ready?.departments ?? []} onSubmit={invite} onClose={() => setInviting(false)} />
      <AlertDialog
        open={suspending !== null}
        onOpenChange={(open) => !open && setSuspending(null)}
        title={t("members.suspendTitle", { name: suspending?.display_name ?? "" })}
        description={t("members.suspendDescription")}
        confirmLabel={t("members.suspendConfirm")}
        destructive
        onConfirm={() => (suspending ? change(suspending, "suspend") : undefined)}
      />
    </section>
  );
}