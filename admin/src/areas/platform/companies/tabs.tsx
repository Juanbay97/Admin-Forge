import type { ReactNode } from "react";
import type { TFunction } from "i18next";
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
export function companyTabs(company: Company, t: TFunction<["platform", "common"]>): CompanyTab[] {
  const readOnly = !company.active;
  return [
    { id: "branding", label: t("companies.detail.tabs.branding"), render: () => <BrandingTab company={company} readOnly={readOnly} /> },
    { id: "keys", label: t("companies.detail.tabs.keys"), render: () => <KeysTab company={company} readOnly={readOnly} /> },
    { id: "models", label: t("companies.detail.tabs.models"), render: () => <ModelsTab company={company} readOnly={readOnly} /> },
    { id: "members", label: t("companies.detail.tabs.members"), render: () => <MembersTab company={company} /> },
    { id: "usage", label: t("companies.detail.tabs.usage"), render: () => <UsageTab company={company} /> },
  ];
}