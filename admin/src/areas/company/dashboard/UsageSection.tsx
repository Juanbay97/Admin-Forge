import { Activity, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { Organization } from "../../../api/account";
import { ApiError } from "../../../api/client";
import type { Services } from "../../../api/services";
import { BarChart } from "../../../charts/BarChart";
import { Delta } from "../../../components/usage/Delta";
import { RangePicker } from "../../../components/usage/RangePicker";
import { useDays } from "../../../components/usage/useDays";
import { filterPeople, shareOf, summarize, topPeople, withDepartments, type Person } from "../../../company/people";
import { formatCostMicros, formatNumber, formatPercent, formatTokens } from "../../../lib/format";
import { changeOf, previousWindow, windowFor } from "../../../platform/range";
import { tokensOf } from "../../../platform/usage";
import { errorMessage } from "../../../shell/errors";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button, buttonVariants } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { Select } from "../../../ui/Select";
import { Skeleton } from "../../../ui/Skeleton";
import { Stat } from "../../../ui/Stat";

/** What each person used, for the range: the company administrator's view (the server shows administrators only their own company). */
export function UsageSection({ services, organization }: { services: Services; organization: Organization }) {
  const { t } = useTranslation(["company", "common"]);
  const orgId = organization.id;
  const [days, setDays] = useDays();
  const current = windowFor(days);
  const before = previousWindow(days);
  const now = useQuery({ queryKey: ["company", orgId, "usage", current], queryFn: () => services.usage.allMembers(orgId, current), retry: false });
  const previous = useQuery({ queryKey: ["company", orgId, "usage", before], queryFn: () => services.usage.allMembers(orgId, before), retry: false });
  const roster = useQuery({ queryKey: ["company", orgId, "members"], queryFn: () => services.members.list(orgId), retry: false });
  const [q, setQ] = useState("");
  const [department, setDepartment] = useState("");

  const people: Person[] = useMemo(() => withDepartments(now.data ?? [], roster.data ?? []), [now.data, roster.data]);
  const totals = summarize(people);
  const earlier = summarize(withDepartments(previous.data ?? [], []));
  const shown = useMemo(() => filterPeople(people, { q, department }), [people, q, department]);
  const ready = now.isSuccess;

  const columns: Column<Person>[] = [
    {
      id: "person",
      header: t("dashboard.columns.person"),
      sortValue: (person) => person.name,
      cell: (person) => (
        <span className="flex flex-col py-1">
          <span className="font-medium text-fg">{person.name}</span>
          <span className="text-caption text-muted">{person.email}</span>
        </span>
      ),
    },
    { id: "department", header: t("dashboard.columns.department"), sortValue: (person) => person.department ?? "", cell: (person) => person.department ?? <span className="text-muted">—</span> },
    { id: "status", header: t("dashboard.columns.status"), sortValue: (person) => person.state, cell: (person) => <Badge tone={person.state === "active" ? "success" : "warning"}>{person.state === "active" ? t("common:memberStatus.active") : t("common:memberStatus.suspended")}</Badge> },
    { id: "requests", header: t("dashboard.columns.requests"), align: "right", sortValue: (person) => person.requests, cell: (person) => formatNumber(person.requests) },
    { id: "tokens", header: t("dashboard.columns.tokens"), align: "right", sortValue: (person) => tokensOf(person), cell: (person) => formatTokens(tokensOf(person)) },
    { id: "cost", header: t("dashboard.columns.cost"), align: "right", sortValue: (person) => person.cost_micros, cell: (person) => formatCostMicros(person.cost_micros) },
    {
      id: "share",
      header: t("dashboard.columns.share"),
      sortValue: (person) => shareOf(person, totals.tokens),
      cell: (person) => {
        const share = shareOf(person, totals.tokens);
        return (
          <span className="flex items-center gap-2">
            <span aria-hidden="true" className="h-2 w-24 overflow-hidden rounded-full bg-subtle">
              <span className="block h-full rounded-full bg-chart-1" style={{ width: `${Math.round(share * 100)}%` }} />
            </span>
            <span className="w-10 tabular-nums text-muted">{formatPercent(share)}</span>
          </span>
        );
      },
    },
  ];

  const departments = organization.departments;
  const nobody = ready && totals.withUsage === 0;
  return (
    <section aria-label={t("dashboard.title")} className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-title text-section font-semibold text-fg">{t("dashboard.title")}</h2>
        <RangePicker days={days} onChange={setDays} />
      </div>
      {now.isError && now.error instanceof ApiError && now.error.status === 404 && (
        <EmptyState icon={Activity} title={t("dashboard.notAvailableTitle")} hint={t("dashboard.notAvailableHint")} />
      )}
      {now.isError && !(now.error instanceof ApiError && now.error.status === 404) && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void now.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(now.error)}</Alert>}
      {now.isPending && <div aria-busy="true"><span className="sr-only">{t("dashboard.loading")}</span><Skeleton className="h-28 w-full" /></div>}
      {ready && totals.unpriced > 0 && <Alert tone="warning">{t("dashboard.unpriced", { count: totals.unpriced })}</Alert>}
      {nobody && (
        <EmptyState
          icon={Activity}
          title={t("dashboard.emptyTitle")}
          hint={t("dashboard.emptyHint")}
          action={<Link to="/company/members" className={buttonVariants({})}>{t("dashboard.invite")}</Link>}
        />
      )}
      {ready && !nobody && (
        <>
          <section aria-label={t("dashboard.keyFigures")}>
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label={t("dashboard.peopleUsing")}>{t("dashboard.peopleOf", { used: totals.withUsage, total: Math.max(totals.people, (roster.data ?? []).length) })}</Stat>
              <Stat label={t("dashboard.tokens")}><span className="flex flex-wrap items-center gap-2">{formatTokens(totals.tokens)}{previous.data && <Delta change={changeOf(totals.tokens, earlier.tokens)} />}</span></Stat>
              <Stat label={t("dashboard.cost")}><span className="flex flex-wrap items-center gap-2">{formatCostMicros(totals.cost_micros)}{previous.data && <Delta change={changeOf(totals.cost_micros, earlier.cost_micros)} />}</span></Stat>
              <Stat label={t("dashboard.requests")}>{formatNumber(totals.requests)}</Stat>
            </dl>
          </section>
          <BarChart id="top-people" title={t("dashboard.topPeople")} items={topPeople(people, 5, "tokens").map((person) => ({ label: person.name, value: tokensOf(person) }))} />
          <DataTable
            caption={t("dashboard.caption")}
            columns={columns}
            rows={shown}
            rowKey={(person) => person.member_id}
            pageSize={15}
            initialSort={{ id: "cost", direction: "desc" }}
            filter={
              <div className="flex flex-wrap items-end gap-3">
                <Field label={t("dashboard.search")} className="min-w-0 flex-1 sm:max-w-sm">
                  {(control) => (
                    <div className="relative">
                      <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                      <Input {...control} type="search" value={q} onChange={(event) => setQ(event.target.value)} placeholder={t("dashboard.searchPlaceholder")} className="pl-9" />
                    </div>
                  )}
                </Field>
                {departments.length > 0 && (
                  <Field label={t("dashboard.department")} className="w-48">
                    {(control) => (
                      <Select {...control} value={department} onChange={(event) => setDepartment(event.target.value)}>
                        <option value="">{t("dashboard.allDepartments")}</option>
                        {departments.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
                      </Select>
                    )}
                  </Field>
                )}
              </div>
            }
            empty={<EmptyState icon={Search} title={t("dashboard.noMatchTitle")} hint={t("dashboard.noMatchHint")} action={<Button variant="outline" onClick={() => { setQ(""); setDepartment(""); }}>{t("dashboard.clearFilters")}</Button>} />}
          />
        </>
      )}
    </section>
  );
}