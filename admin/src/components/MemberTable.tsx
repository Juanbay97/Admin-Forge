import { Search, SearchX, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import type { Department } from "../api/account";
import type { Member } from "../api/members";
import { roleLabel, type PendingInvite } from "../members/model";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { DataTable, type Column } from "../ui/DataTable";
import { EmptyState } from "../ui/EmptyState";
import { Field } from "../ui/Field";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

interface MemberTableProps {
  members: Member[];
  pending: PendingInvite[];
  busyId: string | null;
  loading?: boolean;
  onChange: (member: Member, action: "suspend" | "reactivate") => void;
  /** Opens the invitation dialog from the empty state. */
  onInvite: () => void;
  /** When given, a department filter is offered next to the search. */
  departments?: Department[];
  /** When given (and there are departments), each member row offers "Change department". */
  onAssign?: (member: Member) => void;
}

type Row = { key: string; member: Member } | { key: string; invite: PendingInvite };

const identity = (row: Row) => ("member" in row ? { name: row.member.display_name, email: row.member.email } : { name: row.invite.name, email: row.invite.email });
const department_ = (row: Row) => ("member" in row ? row.member.departments.map((item) => item.name).join(", ") : row.invite.departmentName);
const role = (row: Row) => ("member" in row ? roleLabel(row.member.roles) : "Member");
const status = (row: Row) => ("member" in row ? (row.member.status === "active" ? "Active" : "Suspended") : "Invited");
const TONE = { Active: "success", Suspended: "warning", Invited: "info" } as const;

export function MemberTable({ members, pending, busyId, loading = false, onChange, onInvite, departments = [], onAssign }: MemberTableProps) {
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState("");
  const all: Row[] = useMemo(
    () => [...members.map((member): Row => ({ key: member.id, member })), ...pending.map((invite): Row => ({ key: `invite:${invite.email}`, invite }))],
    [members, pending],
  );
  const needle = query.trim().toLowerCase();
  const rows = all.filter(
    (row) => (!needle || `${identity(row).name} ${identity(row).email}`.toLowerCase().includes(needle)) && (!department || (department_(row)).split(", ").includes(department)),
  );

  const columns: Column<Row>[] = [
    {
      id: "name",
      header: "Name",
      sortValue: (row) => identity(row).name,
      cell: (row) => (
        <>
          <div className="font-medium text-fg">{identity(row).name}</div>
          <div className="text-caption text-muted">{identity(row).email}</div>
        </>
      ),
    },
    { id: "role", header: "Role", sortValue: role, cell: role },
    { id: "departments", header: "Departments", sortValue: department_, cell: department_ },
    {
      id: "status",
      header: "Status",
      sortValue: status,
      cell: (row) => <Badge tone={TONE[status(row) as keyof typeof TONE]}>{status(row)}</Badge>,
    },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (row) =>
        "member" in row ? (
          <div className="flex flex-wrap justify-end gap-2">
            {onAssign && departments.length > 0 && (
              <Button variant="outline" size="sm" disabled={busyId === row.member.id} onClick={() => onAssign(row.member)}>
                Change department
                <span className="sr-only"> of {row.member.display_name}</span>
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={busyId === row.member.id}
              onClick={() => onChange(row.member, row.member.status === "active" ? "suspend" : "reactivate")}
            >
              {row.member.status === "active" ? "Suspend" : "Reactivate"}
              <span className="sr-only"> {row.member.display_name}</span>
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <DataTable
      caption="Organization members"
      loadingLabel="Loading members…"
      loading={loading}
      columns={columns}
      rows={rows}
      rowKey={(row) => row.key}
      pageSize={10}
      filter={
        all.length > 0 || loading ? (
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Search members" className="max-w-sm">
              {(control) => (
                <span className="relative block">
                  <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                  <Input className="pl-9" placeholder="Name or email" value={query} onChange={(event) => setQuery(event.target.value)} {...control} />
                </span>
              )}
            </Field>
            {departments.length > 0 && (
              <Field label="Department" className="w-48">
                {(control) => (
                  <Select {...control} value={department} onChange={(event) => setDepartment(event.target.value)}>
                    <option value="">All departments</option>
                    {[...departments].sort((a, b) => a.name.localeCompare(b.name)).map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
                  </Select>
                )}
              </Field>
            )}
          </div>
        ) : undefined
      }
      empty={
        all.length === 0 ? (
          <EmptyState
            icon={UserPlus}
            title="No members yet"
            hint="Invite the people who should use Forge in your company."
            action={<Button onClick={onInvite}>Invite your first member</Button>}
          />
        ) : (
          <EmptyState icon={SearchX} title="No members match" hint="Try a different name or email address." />
        )
      }
    />
  );
}