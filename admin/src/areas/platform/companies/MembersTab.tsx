import { Search, SearchX, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { Company, CompanyMember } from "../../../api/platform";
import { t as translate } from "../../../i18n/config";
import { roleLabel } from "../../../members/model";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { loadAllMembers } from "./data";

const departments = (member: CompanyMember) => member.departments.map((item) => item.name).join(", ");
const status = (member: CompanyMember) => (member.status === "active" ? translate("memberStatus.active") : translate("memberStatus.suspended"));

const buildColumns = (t: TFunction<["platform", "common"]>): Column<CompanyMember>[] => [
  {
    id: "name",
    header: t("companies.membersTab.columns.name"),
    sortValue: (member) => member.display_name,
    cell: (member) => (
      <>
        <div className="font-medium text-fg">{member.display_name}</div>
        <div className="text-caption text-muted">{member.email}</div>
      </>
    ),
  },
  { id: "role", header: t("companies.membersTab.columns.role"), sortValue: (member) => roleLabel(member.roles), cell: (member) => roleLabel(member.roles) },
  { id: "departments", header: t("companies.membersTab.columns.departments"), sortValue: departments, cell: departments },
  { id: "status", header: t("companies.membersTab.columns.status"), sortValue: status, cell: (member) => <Badge tone={member.status === "active" ? "success" : "warning"}>{status(member)}</Badge> },
];

/** The people of one company as the platform owner sees them: names, roles, departments and status. Read-only by design. */
export function MembersTab({ company }: { company: Company }) {
  const { t } = useTranslation(["platform", "common"]);
  const columns = buildColumns(t);
  const { platform } = useServices();
  const [query, setQuery] = useState("");
  const members = useQuery({ queryKey: ["platform", "company", company.id, "members"], queryFn: () => loadAllMembers(platform, company.id) });
  const needle = query.trim().toLowerCase();
  const rows = useMemo(() => (members.data ?? []).filter((member) => !needle || `${member.display_name} ${member.email}`.toLowerCase().includes(needle)), [members.data, needle]);

  if (members.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void members.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(members.error)}</Alert>;
  return (
    <section className="flex flex-col gap-4">
      <p className="text-body text-muted">{t("companies.membersTab.intro")}</p>
      <DataTable
        caption={t("companies.membersTab.caption")}
        loadingLabel={t("companies.membersTab.loading")}
        loading={members.isPending}
        columns={columns}
        rows={rows}
        rowKey={(member) => member.id}
        pageSize={10}
        filter={
          (members.data?.length ?? 0) > 0 ? (
            <Field label={t("companies.membersTab.search")} className="max-w-sm">
              {(control) => (
                <span className="relative block">
                  <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                  <Input className="pl-9" placeholder={t("companies.membersTab.searchPlaceholder")} value={query} onChange={(event) => setQuery(event.target.value)} {...control} />
                </span>
              )}
            </Field>
          ) : undefined
        }
        empty={
          (members.data?.length ?? 0) === 0 ? (
            <EmptyState icon={Users} title={t("companies.membersTab.emptyNoneTitle")} hint={t("companies.membersTab.emptyNoneHint")} />
          ) : (
            <EmptyState icon={SearchX} title={t("companies.membersTab.emptyNoMatchTitle")} hint={t("companies.membersTab.emptyNoMatchHint")} />
          )
        }
      />
    </section>
  );
}
