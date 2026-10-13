import type { ReactNode } from "react";
import type { Company } from "../../../api/platform";
import { BrandingTab } from "./BrandingTab";
import { KeysTab } from "./KeysTab";
import { MembersTab } from "./MembersTab";
import { ModelsTab } from "./ModelsTab";
import { UsageTab } from "./UsageTab";

export interface CompanyTab {
  id: string;
  label: string;
  render: () => ReactNode;
}

/** The tabs after Overview. A suspended company's tabs are read-only: reactivating is the only way to change anything. */
export function companyTabs(company: Company): CompanyTab[] {
  const readOnly = !company.active;
  return [
    { id: "branding", label: "Branding", render: () => <BrandingTab company={company} readOnly={readOnly} /> },
    { id: "keys", label: "Keys", render: () => <KeysTab company={company} readOnly={readOnly} /> },
    { id: "models", label: "Models", render: () => <ModelsTab company={company} readOnly={readOnly} /> },
    { id: "members", label: "Members", render: () => <MembersTab company={company} /> },
    { id: "usage", label: "Usage", render: () => <UsageTab company={company} /> },
  ];
}