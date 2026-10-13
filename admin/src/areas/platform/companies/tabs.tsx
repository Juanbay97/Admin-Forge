import type { ReactNode } from "react";
import type { Company } from "../../../api/platform";

export interface CompanyTab {
  id: string;
  label: string;
  render: () => ReactNode;
}

/** The tabs after Overview; each later slice (branding, keys, models, usage) adds its own here. */
export function companyTabs(_company: Company): CompanyTab[] {
  return [];
}