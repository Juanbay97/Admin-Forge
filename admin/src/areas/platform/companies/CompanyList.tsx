import { Building2, Plus, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { formatCostMicros, formatTokens } from "../../../lib/format";
import { filterCompanies, parseStatus, type StatusFilter } from "../../../platform/companies";
import { windowFor } from "../../../platform/range";
import { tokensOf } from "../../../platform/usage";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button, buttonVariants } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { PageHeader } from "../../../ui/PageHeader";
import { Select } from "../../../ui/Select";
import { loadAllCompanies } from "./data";

interface Row {
  id: string;
  slug: string;
  display_name: string;
  active: boolean;
  tokens: number | null;
  cost: number | null;
}

export function CompanyList() {
  const { platform } = useServices();
  const [params, setParams] = useSearchParams();
  const status = parseStatus(params.get("status"));
  const urlQuery = params.get("q") ?? "";
  const [text, setText] = useState(urlQuery);
  const window30 = windowFor(30);
  const companies = useQuery({ queryKey: ["platform", "companies", "all"], queryFn: () => loadAllCompanies(platform) });
  const usage = useQuery({ queryKey: ["platform", "usage", "companies", window30], queryFn: () => platform.usageByCompany(window30) });

  // The URL follows what is typed after a short pause, so reload, share and Back keep the search.
  useEffect(() => {
    const handle = setTimeout(() => {
      if (text === urlQuery) return;
      setParams((current) => {
        const next = new URLSearchParams(current);
        if (text) next.set("q", text);
        else next.delete("q");
        return next;
      }, { replace: true });
    }, 300);
    return () => clearTimeout(handle);
  }, [text, urlQuery, setParams]);

  const setStatus = (value: StatusFilter) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (value === "all") next.delete("status");
      else next.set("status", value);
      return next;
    }, { replace: true });

  const rows: Row[] = useMemo(() => {
    const used = new Map((usage.data?.companies ?? []).map((item) => [item.organization_id, item]));
    return filterCompanies(companies.data ?? [], { q: urlQuery, status }).map((company) => {
      const counters = used.get(company.id);
      return { ...company, tokens: counters ? tokensOf(counters) : null, cost: counters ? counters.cost_micros : null };
    });
  }, [companies.data, usage.data, urlQuery, status]);

  const create = <Link to="/platform/companies/new" className={buttonVariants({})}><Plus aria-hidden="true" className="size-4" />Create company</Link>;
  const columns: Column<Row>[] = [
    {
      id: "name",
      header: "Company",
      sortValue: (row) => row.display_name,
      cell: (row) => (
        <span className="flex flex-col py-1">
          <Link to={`/platform/companies/${row.id}`} className="font-medium text-fg underline-offset-4 hover:underline">{row.display_name}</Link>
          <span className="text-caption text-muted">{row.slug}</span>
        </span>
      ),
    },
    { id: "status", header: "Status", sortValue: (row) => Number(row.active), cell: (row) => <Badge tone={row.active ? "success" : "warning"}>{row.active ? "Active" : "Suspended"}</Badge> },
    { id: "tokens", header: "Tokens (30d)", align: "right", sortValue: (row) => row.tokens, cell: (row) => (row.tokens === null ? "—" : formatTokens(row.tokens)) },
    { id: "cost", header: "Cost (30d)", align: "right", sortValue: (row) => row.cost, cell: (row) => (row.cost === null ? "—" : formatCostMicros(row.cost)) },
  ];

  const none = companies.isSuccess && companies.data.length === 0;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Companies" description="Every company on the platform." actions={create} />
      {companies.isError && (
        <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void companies.refetch()}>Try again</Button>}>
          {errorMessage(companies.error)}
        </Alert>
      )}
      <DataTable
        caption="Companies"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        loading={companies.isPending}
        pageSize={20}
        initialSort={{ id: "name", direction: "asc" }}
        filter={
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Search companies" className="min-w-0 flex-1 sm:max-w-sm">
              {(control) => (
                <div className="relative">
                  <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                  <Input {...control} type="search" value={text} onChange={(event) => setText(event.target.value)} placeholder="Name or code" className="pl-9" />
                </div>
              )}
            </Field>
            <Field label="Status" className="w-44">
              {(control) => (
                <Select {...control} value={status} onChange={(event) => setStatus(parseStatus(event.target.value))}>
                  <option value="all">All</option>
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                </Select>
              )}
            </Field>
          </div>
        }
        empty={
          none ? (
            <EmptyState icon={Building2} title="No companies yet" hint="Create the first company: name it, brand it, give it gateway keys and invite its administrator." action={create} />
          ) : (
            <EmptyState icon={Search} title="No companies match" hint="Try another name or code, or clear the filters." action={<Button variant="outline" onClick={() => { setText(""); setStatus("all"); }}>Clear filters</Button>} />
          )
        }
      />
    </section>
  );
}