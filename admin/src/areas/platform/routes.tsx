import { Wizard } from "./companies/wizard/Wizard";
import { KeyPool } from "./keys/KeyPool";
import { Prices } from "./prices/Prices";
import { CompanyDetail } from "./companies/CompanyDetail";
import { CompanyList } from "./companies/CompanyList";
import { Overview } from "./overview/Overview";

export const OverviewRoute = () => <Overview />;
export const CompaniesRoute = () => <CompanyList />;
export const NewCompanyRoute = () => <Wizard />;
export const KeysRoute = () => <KeyPool />;
export const PricesRoute = () => <Prices />;
export const CompanyRoute = () => <CompanyDetail />;