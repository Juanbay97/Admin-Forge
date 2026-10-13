import { Wizard } from "./companies/wizard/Wizard";
import { CompanyDetail } from "./companies/CompanyDetail";
import { CompanyList } from "./companies/CompanyList";
import { Overview } from "./overview/Overview";

export const OverviewRoute = () => <Overview />;
export const CompaniesRoute = () => <CompanyList />;
export const NewCompanyRoute = () => <Wizard />;
export const CompanyRoute = () => <CompanyDetail />;