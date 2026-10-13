import type { Company, PlatformApi } from "../../../api/platform";

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