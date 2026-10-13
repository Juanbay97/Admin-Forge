import type { Department } from "./account";
import type { ApiClient } from "./client";

export interface Member {
  id: string;
  email: string;
  display_name: string;
  status: "active" | "suspended";
  roles: string[];
  departments: Department[];
}

export interface InvitationReceipt {
  invitation_id: string;
  expires_at: string;
  delivery_state: string;
  delivery_channel: string;
}

export interface InviteInput {
  email: string;
  name: string;
  departmentId: string;
}

export interface MembersApi {
  list(orgId: string): Promise<Member[]>;
  suspend(orgId: string, memberId: string): Promise<Member>;
  reactivate(orgId: string, memberId: string): Promise<Member>;
  /** Makes `departmentId` the member's one department; the server answers with the updated member. */
  assignDepartment(orgId: string, memberId: string, departmentId: string): Promise<Member>;
  invite(orgId: string, input: InviteInput): Promise<InvitationReceipt>;
}

export function createMembersApi(client: ApiClient): MembersApi {
  const base = (orgId: string) => `/forge/v1/orgs/${encodeURIComponent(orgId)}/members`;
  const change = (action: "suspend" | "reactivate") => (orgId: string, memberId: string) =>
    client.request<Member>("POST", `${base(orgId)}/${encodeURIComponent(memberId)}/${action}`);
  return {
    async list(orgId) {
      return (await client.request<{ members: Member[] }>("GET", base(orgId))).members;
    },
    suspend: change("suspend"),
    reactivate: change("reactivate"),
    assignDepartment: (orgId, memberId, departmentId) =>
      client.request<Member>("PUT", `${base(orgId)}/${encodeURIComponent(memberId)}/department`, { department_id: departmentId }),
    invite: (orgId, { email, name, departmentId }) =>
      client.request<InvitationReceipt>("POST", "/forge/v1/accounts/invitations", {
        organization_id: orgId,
        department_id: departmentId,
        email,
        name,
      }),
  };
}