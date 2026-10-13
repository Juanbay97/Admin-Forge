import { Activity, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { Organization } from "../../../api/account";
import { ApiError } from "../../../api/client";
import type { Services } from "../../../api/services";
import { BarChart } from "../../../charts/BarChart";
import { Delta } from "../../../components/usage/Delta";
import { RangePicker } from "../../../components/usage/RangePicker";
import { useDays } from "../../../components/usage/useDays";
import { filterPeople, shareOf, summarize, topPeople, withDepartments, type Person } from "../../../company/people";
import { formatCostMicros, formatPercent, formatTokens } from "../../../lib/format";
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
      header: "Person",
      sortValue: (person) => person.name,
      cell: (person) => (
        <span className="flex flex-col py-1">
          <span className="font-medium text-fg">{person.name}</span>
          <span className="text-caption text-muted">{person.email}</span>
        </span>
      ),
    },
    { id: "department", header: "Department", sortValue: (person) => person.department ?? "", cell: (person) => person.department ?? <span className="text-muted">—</span> },
    { id: "status", header: "Status", sortValue: (person) => person.state, cell: (person) => <Badge tone={person.state === "active" ? "success" : "warning"}>{person.state === "active" ? "Active" : "Suspended"}</Badge> },
    { id: "requests", header: "Requests", align: "right", sortValue: (person) => person.requests, cell: (person) => person.requests.toLocaleString("en-US") },
    { id: "tokens", header: "Tokens", align: "right", sortValue: (person) => tokensOf(person), cell: (person) => formatTokens(tokensOf(person)) },
    { id: "cost", header: "Cost", align: "right", sortValue: (person) => person.cost_micros, cell: (person) => formatCostMicros(person.cost_micros) },
    {
      id: "share",
      header: "Share of tokens",
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
    <section aria-label="Usage" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-title text-section font-semibold text-fg">Usage</h2>
        <RangePicker days={days} onChange={setDays} />
      </div>
      {now.isError && now.error instanceof ApiError && now.error.status === 404 && (
        <EmptyState icon={Activity} title="Usage is not available" hint="This server does not report usage for your company yet. Nothing is wrong with your account." />
      )}
      {now.isError && !(now.error instanceof ApiError && now.error.status === 404) && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void now.refetch()}>Try again</Button>}>{errorMessage(now.error)}</Alert>}
      {now.isPending && <div aria-busy="true"><span className="sr-only">Loading usage…</span><Skeleton className="h-28 w-full" /></div>}
      {ready && totals.unpriced > 0 && <Alert tone="warning">{totals.unpriced} {totals.unpriced === 1 ? "request" : "requests"} had no model price, so the cost shown does not include {totals.unpriced === 1 ? "it" : "them"}. Your platform operator sets prices.</Alert>}
      {nobody && (
        <EmptyState
          icon={Activity}
          title="No usage yet"
          hint="Usage appears here after your people send their first request. Invite them and point them at the app download."
          action={<Link to="/company/members" className={buttonVariants({})}>Invite people</Link>}
        />
      )}
      {ready && !nobody && (
        <>
          <section aria-label="Key figures">
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="People using Forge">{totals.withUsage} of {totals.people}</Stat>
              <Stat label="Tokens"><span className="flex flex-wrap items-center gap-2">{formatTokens(totals.tokens)}{previous.data && <Delta change={changeOf(totals.tokens, earlier.tokens)} />}</span></Stat>
              <Stat label="Cost"><span className="flex flex-wrap items-center gap-2">{formatCostMicros(totals.cost_micros)}{previous.data && <Delta change={changeOf(totals.cost_micros, earlier.cost_micros)} />}</span></Stat>
              <Stat label="Requests">{totals.requests.toLocaleString("en-US")}</Stat>
            </dl>
          </section>
          <BarChart id="top-people" title="Top people by tokens" items={topPeople(people, 5, "tokens").map((person) => ({ label: person.name, value: tokensOf(person) }))} />
          <DataTable
            caption="People"
            columns={columns}
            rows={shown}
            rowKey={(person) => person.member_id}
            pageSize={15}
            initialSort={{ id: "cost", direction: "desc" }}
            filter={
              <div className="flex flex-wrap items-end gap-3">
                <Field label="Search people" className="min-w-0 flex-1 sm:max-w-sm">
                  {(control) => (
                    <div className="relative">
                      <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                      <Input {...control} type="search" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Name or email" className="pl-9" />
                    </div>
                  )}
                </Field>
                {departments.length > 0 && (
                  <Field label="Department" className="w-48">
                    {(control) => (
                      <Select {...control} value={department} onChange={(event) => setDepartment(event.target.value)}>
                        <option value="">All departments</option>
                        {departments.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
                      </Select>
                    )}
                  </Field>
                )}
              </div>
            }
            empty={<EmptyState icon={Search} title="No people match" hint="Try another name or clear the department filter." action={<Button variant="outline" onClick={() => { setQ(""); setDepartment(""); }}>Clear filters</Button>} />}
          />
        </>
      )}
    </section>
  );
}