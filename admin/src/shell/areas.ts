// The area registry: which role areas exist, what each one's navigation is and who may enter it. Eager and tiny; the area
// code itself is lazy (see router.tsx). Platform, company and portal are all open.
import type { ParseKeys } from "i18next";
import type { Identity } from "./identity";

/** A key of the `common` catalogue: labels are resolved when rendered, so they follow the active language. */
export type LabelKey = ParseKeys<"common">;

export type AreaId = "platform" | "company" | "portal";
export type IconName = "gauge" | "users" | "plug" | "layers" | "palette" | "shield" | "building" | "download" | "chart" | "home";

export interface NavEntry {
  labelKey: LabelKey;
  to: string;
  icon: IconName;
  requires?: (identity: Identity) => boolean;
}

export interface AreaManifest {
  id: AreaId;
  basePath: `/${AreaId}`;
  labelKey: LabelKey;
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
    labelKey: "areas.platform",
    enabled: true,
    requires: (identity) => identity.platform?.role === "platform_owner",
    nav: [
      { labelKey: "nav.platform.overview", to: "/platform", icon: "gauge" },
      { labelKey: "nav.platform.companies", to: "/platform/companies", icon: "building" },
      { labelKey: "nav.platform.keys", to: "/platform/keys", icon: "plug" },
      { labelKey: "nav.platform.prices", to: "/platform/prices", icon: "layers" },
      { labelKey: "nav.platform.audit", to: "/platform/audit", icon: "shield" },
    ],
  },
  company: {
    id: "company",
    basePath: "/company",
    labelKey: "areas.company",
    enabled: true,
    requires: (identity) => identity.orgs.some((organization) => organization.roles.includes(ADMIN_ROLE)),
    nav: [
      { labelKey: "nav.company.overview", to: "/company", icon: "gauge" },
      { labelKey: "nav.company.members", to: "/company/members", icon: "users" },
      { labelKey: "nav.company.gateway", to: "/company/gateway", icon: "plug" },
      { labelKey: "nav.company.catalog", to: "/company/catalog", icon: "layers" },
      { labelKey: "nav.company.branding", to: "/company/branding", icon: "palette" },
      { labelKey: "nav.company.download", to: "/company/download", icon: "download" },
    ],
  },
  portal: {
    id: "portal",
    basePath: "/portal",
    labelKey: "areas.portal",
    enabled: true,
    requires: (identity) => identity.orgs.length > 0,
    nav: [
      { labelKey: "nav.portal.home", to: "/portal", icon: "home" },
      { labelKey: "nav.portal.download", to: "/portal/download", icon: "download" },
      { labelKey: "nav.portal.usage", to: "/portal/usage", icon: "chart" },
    ],
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