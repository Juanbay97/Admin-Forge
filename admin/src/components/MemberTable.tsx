import type { Member } from "../api/members";
import { roleLabel, type PendingInvite } from "../members/model";

interface MemberTableProps {
  members: Member[];
  pending: PendingInvite[];
  busyId: string | null;
  onChange: (member: Member, action: "suspend" | "reactivate") => void;
}

const CELL = "px-3 py-2 text-left align-top";

export function MemberTable({ members, pending, busyId, onChange }: MemberTableProps) {
  return (
    <table className="w-full border-collapse overflow-hidden rounded-lg bg-white text-sm shadow">
      <caption className="sr-only">Organization members</caption>
      <thead className="bg-primary text-sand">
        <tr>
          {["Name", "Role", "Departments", "Status", "Actions"].map((heading) => (
            <th key={heading} scope="col" className={CELL}>
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {members.map((member) => (
          <tr key={member.id} className="border-t border-carbon/15">
            <td className={CELL}>
              <div className="font-medium">{member.display_name}</div>
              <div>{member.email}</div>
            </td>
            <td className={CELL}>{roleLabel(member.roles)}</td>
            <td className={CELL}>{member.departments.map((department) => department.name).join(", ")}</td>
            <td className={CELL}>{member.status === "active" ? "Active" : "Suspended"}</td>
            <td className={CELL}>
              <button
                type="button"
                disabled={busyId === member.id}
                onClick={() => onChange(member, member.status === "active" ? "suspend" : "reactivate")}
                className="rounded border border-teal px-3 py-1 text-teal transition-colors hover:bg-teal hover:text-white disabled:opacity-60"
              >
                {member.status === "active" ? "Suspend" : "Reactivate"}
                <span className="sr-only"> {member.display_name}</span>
              </button>
            </td>
          </tr>
        ))}
        {pending.map((invite) => (
          <tr key={invite.email} className="border-t border-carbon/15">
            <td className={CELL}>
              <div className="font-medium">{invite.name}</div>
              <div>{invite.email}</div>
            </td>
            <td className={CELL}>Member</td>
            <td className={CELL}>{invite.departmentName}</td>
            <td className={CELL}>Invited</td>
            <td className={CELL} />
          </tr>
        ))}
      </tbody>
    </table>
  );
}