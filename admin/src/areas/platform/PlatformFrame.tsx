import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { Outlet } from "react-router";
import { platformTheme } from "../../brand/platformTheme";
import { AREAS } from "../../shell/areas";
import { AppShell } from "../../shell/AppShell";
import { useServices } from "../../shell/services";
import { loadAllCompanies } from "./companies/data";

/** The shell once the second factor has passed: its palette can jump to any company (the list is the same cached query the pages use). */
export function PlatformFrame({ switcher }: { switcher: ReactNode }) {
  const { platform } = useServices();
  const companies = useQuery({ queryKey: ["platform", "companies", "all"], queryFn: () => loadAllCompanies(platform) });
  const commands = useMemo(() => (companies.data ?? []).map((company) => ({ label: company.display_name, hint: company.slug, to: `/platform/companies/${company.id}` })), [companies.data]);
  return (
    <AppShell area={AREAS.platform} brand={platformTheme} switcher={switcher} commands={commands}>
      <Outlet />
    </AppShell>
  );
}