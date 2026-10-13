import { z } from "../lib/zod";
import { ApiError, type ApiClient } from "./client";

// `POST /forge/v1/accounts/invitations/accept`: the response carries ids only (no email; that response is part of the pinned contract). The
// hidden `POST .../invitations/preview` (not part of the contract) names who an unused invitation is for, so the join page does not ask.
const Enrollment = z.strictObject({ account_id: z.string().uuid(), organization_id: z.string().uuid(), membership_id: z.string().uuid(), department_id: z.string().uuid() });
export type Enrollment = z.infer<typeof Enrollment>;

const Preview = z.strictObject({ account_email: z.string().min(3), display_name: z.string() });

/** `known`: the invitation is usable and this is who it is for. `unusable`: the server's uniform 404 (expired, used, withdrawn, wrong or unknown: never told apart).
 * `unsupported`: an older server without the route; the page asks for the email as it always did. */
export type InvitationPreview = { kind: "known"; email: string; name: string } | { kind: "unusable" } | { kind: "unsupported" };

export interface InvitationsApi {
  accept(input: { invitationId: string; capability: string; password: string }): Promise<Enrollment>;
  preview(input: { invitationId: string; capability: string }): Promise<InvitationPreview>;
}

export function createInvitationsApi(client: ApiClient): InvitationsApi {
  return {
    async accept({ invitationId, capability, password }) {
      const raw = await client.request("POST", "/forge/v1/accounts/invitations/accept", { invitation_id: invitationId, capability, password });
      const parsed = Enrollment.safeParse(raw);
      if (!parsed.success) throw new ApiError(200, "INVALID_RESPONSE", "The server sent an unexpected enrollment.");
      return parsed.data;
    },
    async preview({ invitationId, capability }) {
      let raw: unknown;
      try {
        raw = await client.request("POST", "/forge/v1/accounts/invitations/preview", { invitation_id: invitationId, capability });
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return error.code === "NOT_FOUND" ? { kind: "unusable" } : { kind: "unsupported" };
        if (error instanceof ApiError && error.status === 405) return { kind: "unsupported" };
        throw error;
      }
      const parsed = Preview.safeParse(raw);
      if (!parsed.success) throw new ApiError(200, "INVALID_RESPONSE", "The server sent an unexpected invitation.");
      return { kind: "known", email: parsed.data.account_email, name: parsed.data.display_name };
    },
  };
}