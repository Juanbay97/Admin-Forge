import { z } from "../lib/zod";
import { ApiError, type ApiClient } from "./client";

// `POST /forge/v1/accounts/invitations/accept`: the response carries ids only (no email), so the join page asks for the email once.
const Enrollment = z.strictObject({ account_id: z.string().uuid(), organization_id: z.string().uuid(), membership_id: z.string().uuid(), department_id: z.string().uuid() });
export type Enrollment = z.infer<typeof Enrollment>;

export interface InvitationsApi {
  accept(input: { invitationId: string; capability: string; password: string }): Promise<Enrollment>;
}

export function createInvitationsApi(client: ApiClient): InvitationsApi {
  return {
    async accept({ invitationId, capability, password }) {
      const raw = await client.request("POST", "/forge/v1/accounts/invitations/accept", { invitation_id: invitationId, capability, password });
      const parsed = Enrollment.safeParse(raw);
      if (!parsed.success) throw new ApiError(200, "INVALID_RESPONSE", "The server sent an unexpected enrollment.");
      return parsed.data;
    },
  };
}