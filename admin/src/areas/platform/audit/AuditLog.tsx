import { ScrollText } from "lucide-react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import type { AuditEntry } from "../../../api/platform";
import { formatDateTime } from "../../../lib/format";
import { KNOWN_ACTIONS, describeAction, filterEntries, relativeTime } from "../../../platform/audit";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { PageHeader } from "../../../ui/PageHeader";
import { Select } from "../../../ui/Select";
import { loadAllCompanies } from "../companies/data";

const PAGE = 50;

export function AuditLog() {
  const { platform } = useServices();
  const [params, setParams] = useSearchParams();
  const filter = { action: params.get("action") ?? "", company: params.get("company") ?? "", from: params.get("from") ?? "", to: params.get("to") ?? "" };
  const set = (key: keyof typeof filter, value: string) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    }, { replace: true });

  const log = useInfiniteQuery({
    queryKey: ["platform", "audit", "log"],
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }) => platform.audit({ before: pageParam, page: PAGE }),
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
  const companies = useQuery({ queryKey: ["platform", "companies", "all"], queryFn: () => loadAllCompanies(platform) });
  const names = useMemo(() => new Map((companies.data ?? []).map((company) => [company.id, company.display_name])), [companies.data]);
  const loaded = useMemo(() => (log.data?.pages ?? []).flatMap((page) => page.entries), [log.data]);
  const rows = useMemo(() => filterEntries(loaded, filter), [loaded, filter.action, filter.company, filter.from, filter.to]); // eslint-disable-line react-hooks/exhaustive-deps

  const columns: Column<AuditEntry>[] = [
    {
      id: "time",
      header: "When",
      cell: (entry) => (
        <span className="flex flex-col py-1">
          <time dateTime={entry.recorded_at} className="font-medium text-fg">{relativeTime(entry.recorded_at)}</time>
          <span className="text-caption text-muted">{formatDateTime(entry.recorded_at)}</span>
        </span>
      ),
    },
    { id: "action", header: "Action", cell: (entry) => describeAction(entry.action) },
    { id: "target", header: "Company", cell: (entry) => (entry.organization_id ? (names.get(entry.organization_id) ?? "Unknown company") : <span className="text-muted">Platform</span>) },
    { id: "actor", header: "By", cell: () => "Platform owner" },
  ];

  const narrowed = filter.action || filter.company || filter.from || filter.to;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Audit log" description="Everything the platform owner did, newest first. Read-only." />
      {log.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void log.refetch()}>Try again</Button>}>{errorMessage(log.error)}</Alert>}
      <DataTable
        caption="Audit log"
        columns={columns}
        rows={rows}
        rowKey={(entry) => String(entry.id)}
        loading={log.isPending}
        pageSize={500}
        filter={
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Action" className="w-56">
              {(control) => (
                <Select {...control} value={filter.action} onChange={(event) => set("action", event.target.value)}>
                  <option value="">All actions</option>
                  {KNOWN_ACTIONS.map((action) => <option key={action} value={action}>{describeAction(action)}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Company" className="w-56">
              {(control) => (
                <Select {...control} value={filter.company} onChange={(event) => set("company", event.target.value)}>
                  <option value="">All companies</option>
                  {(companies.data ?? []).map((company) => <option key={company.id} value={company.id}>{company.display_name}</option>)}
                </Select>
              )}
            </Field>
            <Field label="From" className="w-44">{(control) => <Input {...control} type="date" value={filter.from} onChange={(event) => set("from", event.target.value)} />}</Field>
            <Field label="To" className="w-44">{(control) => <Input {...control} type="date" value={filter.to} onChange={(event) => set("to", event.target.value)} />}</Field>
          </div>
        }
        empty={
          <EmptyState
            icon={ScrollText}
            title={narrowed && loaded.length > 0 ? "No matching events" : "Nothing recorded yet"}
            hint={narrowed && loaded.length > 0 ? "No loaded event matches these filters. Load older events or clear a filter." : "Actions taken in this console appear here."}
            action={narrowed ? <Button variant="outline" onClick={() => setParams({}, { replace: true })}>Clear filters</Button> : undefined}
          />
        }
      />
      {log.hasNextPage && (
        <div><Button variant="outline" loading={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()}>Load more</Button></div>
      )}
    </section>
  );
}