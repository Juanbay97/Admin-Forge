import type { Me, Organization } from "../api/account";

export const ADMIN_ROLE = "organization_admin";

export type Entry =
  | { kind: "denied" }
  | { kind: "ready"; organization: Organization }
  | { kind: "choose"; organizations: Organization[] };

export function adminOrganizations(me: Me): Organization[] {
  return me.organizations.filter((organization) => organization.roles.includes(ADMIN_ROLE));
}

/** Only administered organisations count; one is entered directly, several need a choice. */
export function resolveEntry(me: Me): Entry {
  const organizations = adminOrganizations(me);
  const [only, ...others] = organizations;
  if (!only) return { kind: "denied" };
  return others.length === 0 ? { kind: "ready", organization: only } : { kind: "choose", organizations };
}