import { ApiError } from "../api/client";
import type { Member } from "../api/members";
import { ADMIN_ROLE } from "../auth/access";

/** An invitation sent in this session; the server lists members only once they accept. */
export interface PendingInvite {
  email: string;
  name: string;
  departmentName: string;
}

export type Action = "load" | "suspend" | "reactivate" | "invite" | "assign";

export const roleLabel = (roles: string[]) => (roles.includes(ADMIN_ROLE) ? "Administrator" : "Member");

export const applyUpdate = (members: Member[], updated: Member) =>
  members.map((member) => (member.id === updated.id ? updated : member));

export const visiblePending = (pending: PendingInvite[], members: Member[]) => {
  const joined = new Set(members.map((member) => member.email.toLowerCase()));
  return pending.filter((invite) => !joined.has(invite.email.toLowerCase()));
};

/** Server detail is never shown: messages are fixed, redacted and say what to do next. */
export function describeFailure(failure: unknown, action: Action): string {
  const error = failure instanceof ApiError ? failure : null;
  if (error?.code === "LAST_ADMIN") {
    return "This is the last administrator. Make another member an administrator before suspending this one.";
  }
  if (error?.status === 404 && (action === "suspend" || action === "reactivate")) {
    return "This member is no longer available. Reload the list.";
  }
  if (action === "assign") return "The department could not be changed. It may no longer exist; reload the page and try again.";
  if (action === "invite") return "The invitation could not be sent. Check the name and email, then try again.";
  if (action === "load") return "The members could not be loaded. Try again.";
  return "The change could not be saved. Try again.";
}