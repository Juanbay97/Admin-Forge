// The area registry: which role areas exist, what each one's navigation is and who may enter it. Eager and tiny; the area
// code itself is lazy (see router.tsx). The portal is a registered stub until its own change enables it.
import type { Identity } from "./identity";

export type AreaId = "platform" | "company" | "portal";
export type IconName = "gauge" | "users" | "plug" | "layers" | "palette" | "shield" | "building";

export interface NavEntry {
  label: string;
  to: string;
  icon: IconName;
  requires?: (identity: Identity) => boolean;
}

export interface AreaManifest {
  id: AreaId;
  basePath: `/${AreaId}`;
  label: string;
  /** A disabled area is registered but not navigable: its paths are "not found" for everyone. */
  enabled: boolean;
  requires: (identity: Identity) => boolean;
  nav: NavEntry[];
}

export const ADMIN_ROLE = "organization_admin";

export const AREAS: Record<AreaId, AreaManifest> = {
  platform: {
    id: "platform",
    basePath: "/platform",
    label: "Platform",
    enabled: true,
    requires: (identity) => identity.platform?.role === "platform_owner",
    nav: [
      { label: "Overview", to: "/platform", icon: "gauge" },
      { label: "Companies", to: "/platform/companies", icon: "building" },
      { label: "Gateway keys", to: "/platform/keys", icon: "plug" },
      { label: "Prices", to: "/platform/prices", icon: "layers" },
      { label: "Audit log", to: "/platform/audit", icon: "shield" },
    ],
  },
  company: {
    id: "company",
    basePath: "/company",
    label: "Company",
    enabled: true,
    requires: (identity) => identity.orgs.some((organization) => organization.roles.includes(ADMIN_ROLE)),
    nav: [
      { label: "Overview", to: "/company", icon: "gauge" },
      { label: "Members", to: "/company/members", icon: "users" },
      { label: "Gateway", to: "/company/gateway", icon: "plug" },
      { label: "Catalog", to: "/company/catalog", icon: "layers" },
      { label: "Branding", to: "/company/branding", icon: "palette" },
    ],
  },
  portal: {
    id: "portal",
    basePath: "/portal",
    label: "Portal",
    enabled: false,
    requires: (identity) => identity.orgs.length > 0,
    nav: [],
  },
};

export function areaOfPath(pathname: string): AreaId | null {
  const first = pathname.split("/")[1];
  return first && first in AREAS ? (first as AreaId) : null;
}

export function navFor(area: AreaManifest, identity: Identity): NavEntry[] {
  return area.nav.filter((entry) => !entry.requires || entry.requires(identity));
}

/** The area a signed-in user lands on: their natural home when it is open, otherwise the first open area they may enter. */
export function enterableArea(identity: Identity, preferred: AreaId): AreaManifest | null {
  const order: AreaId[] = [preferred, "platform", "company", "portal"];
  for (const id of order) {
    const area = AREAS[id];
    if (area.enabled && area.requires(identity)) return area;
  }
  return null;
}