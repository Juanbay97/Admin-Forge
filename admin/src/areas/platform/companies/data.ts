import type { Company, CompanyMember, PlatformApi } from "../../../api/platform";

const PAGE = 100;
const MAX_PAGES = 20;

/** Every company, following the slug cursor (the server pages by company code and has no filters of its own). */
export async function loadAllCompanies(api: Pick<PlatformApi, "companies">): Promise<Company[]> {
  const all: Company[] = [];
  let after: string | undefined;
  for (let index = 0; index < MAX_PAGES; index += 1) {
    const page = await api.companies({ after, page: PAGE });
    all.push(...page.companies);
    if (!page.next_after) break;
    after = page.next_after;
  }
  return all;
}
/** Every member of one company, following the membership cursor (at most 100 per page, a safety stop at 2,000 people). */
export async function loadAllMembers(api: Pick<PlatformApi, "companyMembers">, companyId: string): Promise<CompanyMember[]> {
  const all: CompanyMember[] = [];
  let after: string | undefined;
  for (let index = 0; index < MAX_PAGES; index += 1) {
    const page = await api.companyMembers(companyId, { after, page: PAGE });
    all.push(...page.members);
    if (!page.next_after) break;
    after = page.next_after;
  }
  return all;
}
