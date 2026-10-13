import { Search, SearchX, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { Company, CompanyMember } from "../../../api/platform";
import { roleLabel } from "../../../members/model";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { loadAllMembers } from "./data";

const departments = (member: CompanyMember) => member.departments.map((item) => item.name).join(", ");
const status = (member: CompanyMember) => (member.status === "active" ? "Active" : "Suspended");

const columns: Column<CompanyMember>[] = [
  {
    id: "name",
    header: "Name",
    sortValue: (member) => member.display_name,
    cell: (member) => (
      <>
        <div className="font-medium text-fg">{member.display_name}</div>
        <div className="text-caption text-muted">{member.email}</div>
      </>
    ),
  },
  { id: "role", header: "Role", sortValue: (member) => roleLabel(member.roles), cell: (member) => roleLabel(member.roles) },
  { id: "departments", header: "Departments", sortValue: departments, cell: departments },
  { id: "status", header: "Status", sortValue: status, cell: (member) => <Badge tone={member.status === "active" ? "success" : "warning"}>{status(member)}</Badge> },
];

/** The people of one company as the platform owner sees them: names, roles, departments and status. Read-only by design. */
export function MembersTab({ company }: { company: Company }) {
  const { platform } = useServices();
  const [query, setQuery] = useState("");
  const members = useQuery({ queryKey: ["platform", "company", company.id, "members"], queryFn: () => loadAllMembers(platform, company.id) });
  const needle = query.trim().toLowerCase();
  const rows = useMemo(() => (members.data ?? []).filter((member) => !needle || `${member.display_name} ${member.email}`.toLowerCase().includes(needle)), [members.data, needle]);

  if (members.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void members.refetch()}>Try again</Button>}>{errorMessage(members.error)}</Alert>;
  return (
    <section className="flex flex-col gap-4">
      <p className="text-body text-muted">The people of this company, as its administrators see them. Changes are made by the company's own administrators.</p>
      <DataTable
        caption="Company members"
        loadingLabel="Loading members"
        loading={members.isPending}
        columns={columns}
        rows={rows}
        rowKey={(member) => member.id}
        pageSize={10}
        filter={
          (members.data?.length ?? 0) > 0 ? (
            <Field label="Search members" className="max-w-sm">
              {(control) => (
                <span className="relative block">
                  <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                  <Input className="pl-9" placeholder="Name or email" value={query} onChange={(event) => setQuery(event.target.value)} {...control} />
                </span>
              )}
            </Field>
          ) : undefined
        }
        empty={
          (members.data?.length ?? 0) === 0 ? (
            <EmptyState icon={Users} title="No members yet" hint="People appear here once they accept their invitation." />
          ) : (
            <EmptyState icon={SearchX} title="No members match" hint="Try a different name or email address." />
          )
        }
      />
    </section>
  );
}
