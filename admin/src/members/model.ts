import { ApiError } from "../api/client";
import type { Member } from "../api/members";
import { ADMIN_ROLE } from "../auth/access";
import { t } from "../i18n/config";

/** An invitation sent in this session; the server lists members only once they accept. */
export interface PendingInvite {
  email: string;
  name: string;
  departmentName: string;
}

export type Action = "load" | "suspend" | "reactivate" | "invite" | "assign";

export const roleLabel = (roles: string[]) => (roles.includes(ADMIN_ROLE) ? t("roles.administrator") : t("roles.member"));

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
    return t("members.failure.lastAdmin");
  }
  if (error?.status === 404 && (action === "suspend" || action === "reactivate")) {
    return t("members.failure.gone");
  }
  if (action === "assign") return t("members.failure.assign");
  if (action === "invite") return t("members.failure.invite");
  if (action === "load") return t("members.failure.load");
  return t("members.failure.save");
}