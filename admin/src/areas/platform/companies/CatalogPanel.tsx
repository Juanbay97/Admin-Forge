import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers, Search } from "lucide-react";
import { useId, useState } from "react";
import type { CatalogDiscovery, CatalogRead, Company } from "../../../api/platform";
import { effectiveDefault, publicationLabel, validateSelection, type Row } from "../../../catalog/model";
import { buildRows, describeCatalogFailure, filterRows, KEY_STATES, mergeDiscovery, preferredDefault } from "../../../catalog/platformModel";
import { formatDateTime } from "../../../lib/format";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { EmptyState } from "../../../ui/EmptyState";
import { Input } from "../../../ui/Input";
import { Skeleton } from "../../../ui/Skeleton";
import { useToast } from "../../../ui/toast/Toast";

type Configured = Extract<CatalogRead, { configured: true }>;

/**
 * The platform owner's catalog for one company: discover what the assigned keys can reach, pick the models (or combos) the company
 * may use with an alias each and one default, and publish. Publishing also makes the selected models the company's allowed set.
 */
export function CatalogPanel({ company, readOnly }: { company: Company; readOnly: boolean }) {
  const { platform } = useServices();
  const read = useQuery({ queryKey: ["platform", "company", company.id, "catalog"], queryFn: () => platform.catalog(company.id) });
  if (read.isError) {
    return (
      <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void read.refetch()}>Try again</Button>}>
        {describeCatalogFailure(read.error, "load")}
      </Alert>
    );
  }
  if (!read.data) return <Skeleton className="h-40 w-full" />;
  if (!read.data.configured) {
    return (
      <Alert tone="info" title="No gateway key assigned">
        Assign at least one gateway key to this company in the Keys tab, then come back to discover the models it can use.
      </Alert>
    );
  }
  return <Editor key={`${company.id}:${read.data.catalogue.revision}`} company={company} readOnly={readOnly} current={read.data} />;
}

function Editor({ company, readOnly, current }: { company: Company; readOnly: boolean; current: Configured }) {
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const searchId = useId();
  const { catalogue } = current;
  const [rows, setRows] = useState<Row[]>(() => buildRows(current.discovered?.model_ids ?? [], catalogue.aliases));
  const [preferred, setPreferred] = useState(() => preferredDefault(catalogue.aliases, catalogue.default_model));
  const [query, setQuery] = useState("");
  const [probe, setProbe] = useState<CatalogDiscovery | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const queryKey = ["platform", "company", company.id, "catalog"];

  const discover = useMutation({
    mutationFn: () => platform.discoverModels(company.id),
    onSuccess: (found) => {
      setProbe(found);
      setProblems([]);
      if (found.discovered_at) {
        setRows((previous) => mergeDiscovery(previous, found.model_ids));
        const next: CatalogRead = { ...current, discovered: { model_ids: found.model_ids, at: found.discovered_at } };
        client.setQueryData(queryKey, next);
      }
      void client.invalidateQueries({ queryKey: ["platform", "audit"] });
    },
  });

  const publish = useMutation({
    mutationFn: (selection: { aliases: Record<string, string>; defaultAlias: string }) =>
      platform.publishCatalog(company.id, { expectedCatalogueRevision: catalogue.revision, expectedGatewayRevision: current.gateway_revision, ...selection }),
    onSuccess: (done) => {
      toast.push({ tone: "success", title: "Catalog published", message: `${done.models.length} ${done.models.length === 1 ? "model" : "models"}, default ${done.default_model}.` });
      void client.invalidateQueries({ queryKey });
      void client.invalidateQueries({ queryKey: ["platform", "company", company.id, "models"] });
      void client.invalidateQueries({ queryKey: ["platform", "audit"] });
    },
  });

  const edit = (upstream: string, change: Partial<Row>) => setRows((previous) => previous.map((row) => (row.upstream === upstream ? { ...row, ...change } : row)));
  const shown = filterRows(rows, query);
  const selected = rows.filter((row) => row.selected).length;
  const chosenDefault = effectiveDefault(rows, preferred);
  const setShown = (value: boolean) => {
    const ids = new Set(shown.map((row) => row.upstream));
    setRows((previous) => previous.map((row) => (ids.has(row.upstream) ? { ...row, selected: value } : row)));
  };
  const submit = () => {
    const result = validateSelection(rows, chosenDefault);
    setProblems(result.ok ? [] : result.problems);
    if (result.ok) publish.mutate({ aliases: result.aliases, defaultAlias: result.defaultAlias });
  };
  const missing = Object.values(catalogue.aliases).filter((upstream) => !rows.some((row) => row.upstream === upstream));

  return (
    <section aria-label="Catalog" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={catalogue.state === "CURRENT" ? "success" : "warning"}>{publicationLabel(catalogue.state)}</Badge>
            <span className="text-body text-muted">Catalog revision {catalogue.revision}</span>
          </div>
          <p className="text-caption text-muted">Last discovered: {current.discovered ? formatDateTime(current.discovered.at) : "never"}</p>
        </div>
        {!readOnly && (
          <Button variant="outline" loading={discover.isPending} onClick={() => discover.mutate()}>
            Discover models
          </Button>
        )}
      </div>

      {discover.isError && <Alert tone="destructive">{describeCatalogFailure(discover.error, "discover")}</Alert>}
      {probe && <KeyStates probe={probe} />}
      {probe && !probe.discovered_at && (
        <Alert tone="warning">No key answered, so nothing was stored. The models below are from the last successful discovery.</Alert>
      )}

      {rows.length === 0 ? (
        <EmptyState icon={Layers} title="No models discovered yet" hint={readOnly ? "Reactivate the company to discover models." : "Use Discover models to ask the assigned keys what they can reach."} />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-1.5 sm:max-w-sm">
              <label htmlFor={searchId} className="text-body font-medium text-fg">Search models</label>
              <div className="relative">
                <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <Input id={searchId} className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} autoComplete="off" spellCheck={false} placeholder="e.g. gpt or combo" />
              </div>
            </div>
            {!readOnly && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setShown(true)} disabled={shown.length === 0}>Select shown</Button>
                <Button variant="outline" size="sm" onClick={() => setShown(false)} disabled={shown.length === 0}>Clear shown</Button>
              </div>
            )}
          </div>
          <p role="status" className="text-caption text-muted">
            {selected} of {rows.length} selected{query.trim() ? ` · ${shown.length} shown` : ""}
          </p>
          {shown.length === 0 ? (
            <p className="rounded-card border border-line p-4 text-body text-muted">No model matches "{query.trim()}".</p>
          ) : (
            <ul aria-label="Discovered models" className="flex flex-col divide-y divide-line rounded-card border border-line">
              {shown.map((row) => (
                <li key={row.upstream} className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 px-3 py-2 sm:grid-cols-[auto_minmax(0,1fr)_14rem_auto]">
                  <input type="checkbox" className="size-5 cursor-pointer accent-action" aria-label={`Select ${row.upstream}`} checked={row.selected} disabled={readOnly} onChange={(event) => edit(row.upstream, { selected: event.target.checked })} />
                  <span className="min-w-0 break-all font-mono text-body text-fg">{row.upstream}</span>
                  <Input aria-label={`Alias for ${row.upstream}`} className="col-start-2 sm:col-start-auto" value={row.alias} disabled={readOnly || !row.selected} onChange={(event) => edit(row.upstream, { alias: event.target.value })} autoComplete="off" spellCheck={false} />
                  <label className="col-start-2 flex min-h-10 cursor-pointer items-center gap-2 text-caption text-muted sm:col-start-auto">
                    <input type="radio" name="default-model" className="size-5 cursor-pointer accent-action" aria-label={`Default model ${row.upstream}`} checked={row.selected && chosenDefault === row.upstream} disabled={readOnly || !row.selected} onChange={() => setPreferred(row.upstream)} />
                    Default
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {missing.length > 0 && <Alert tone="warning">Published but not in the latest discovery: {missing.join(", ")}. Publishing again drops them.</Alert>}
      {problems.length > 0 && (
        <Alert tone="destructive" title="Check the selection">
          <ul className="list-disc pl-5">
            {problems.map((problem) => <li key={problem}>{problem}</li>)}
          </ul>
        </Alert>
      )}
      {publish.isError && <Alert tone="destructive">{describeCatalogFailure(publish.error, "publish")}</Alert>}
      {readOnly ? (
        <Alert tone="info">Reactivate the company to change its catalog.</Alert>
      ) : (
        <div>
          <Button loading={publish.isPending} disabled={rows.length === 0} onClick={submit}>Publish catalog</Button>
        </div>
      )}
    </section>
  );
}

function KeyStates({ probe }: { probe: CatalogDiscovery }) {
  if (probe.keys.length === 0) return <Alert tone="info">No keys are assigned to this company.</Alert>;
  return (
    <ul aria-label="Key discovery" className="flex flex-col divide-y divide-line rounded-card border border-line">
      {probe.keys.map((key) => {
        const state = KEY_STATES[key.state];
        return (
          <li key={key.key_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
            <span className="font-medium text-fg">{key.label}</span>
            <Badge tone={state.tone}>{state.label}</Badge>
            {key.state === "ok" ? (
              <span className="text-caption text-muted">{key.model_count} {key.model_count === 1 ? "model" : "models"}</span>
            ) : (
              <span className="text-caption text-muted">{state.hint}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
