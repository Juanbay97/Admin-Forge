import { Layers } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "../../../api/client";
import type { Company } from "../../../api/platform";
import { describeCatalogFailure } from "../../../catalog/platformModel";
import { usd } from "../../../platform/money";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Skeleton } from "../../../ui/Skeleton";
import { useToast } from "../../../ui/toast/Toast";
import { CatalogPanel } from "./CatalogPanel";

const NOTHING_DISCOVERED = "Refresh the models from the company's keys first; allowed models are chosen from what the keys can reach.";

type Price = { upstream_id: string; input_micros: number; output_micros: number; version: number };

export function ModelsTab({ company, readOnly }: { company: Company; readOnly: boolean }) {
  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="catalog-heading" className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 id="catalog-heading" className="font-title text-card font-semibold text-fg">Catalog</h2>
          <p className="text-body text-muted">Discover the models this company's keys can reach, choose which ones it may use under which names, and publish. Company administrators see the published catalog and can only narrow it.</p>
        </div>
        <CatalogPanel company={company} readOnly={readOnly} />
      </section>
      <section aria-labelledby="allowed-heading" className="flex flex-col gap-3">
        <h2 id="allowed-heading" className="font-title text-card font-semibold text-fg">Allowed models</h2>
        <AllowedModels company={company} readOnly={readOnly} />
      </section>
    </div>
  );
}

/** The ceiling is never typed: it is chosen among the models the company's keys were discovered to reach. */
function AllowedModels({ company, readOnly }: { company: Company; readOnly: boolean }) {
  const { platform } = useServices();
  const access = useQuery({ queryKey: ["platform", "company", company.id, "models"], queryFn: () => platform.modelAccess(company.id) });
  // The same query as the catalog panel above: a discovery or a publication there refreshes this list too.
  const catalog = useQuery({ queryKey: ["platform", "company", company.id, "catalog"], queryFn: () => platform.catalog(company.id) });
  const prices = useQuery({ queryKey: ["platform", "prices"], queryFn: () => platform.prices() });
  if (access.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void access.refetch()}>Try again</Button>}>{errorMessage(access.error)}</Alert>;
  if (catalog.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void catalog.refetch()}>Try again</Button>}>{describeCatalogFailure(catalog.error, "load")}</Alert>;
  if (!access.data || !catalog.data) return <Skeleton className="h-40 w-full" />;
  const discovered = catalog.data.configured ? (catalog.data.discovered?.model_ids ?? []) : [];
  const pricing = prices.data?.prices ?? [];
  if (discovered.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <Alert tone="info">{NOTHING_DISCOVERED}</Alert>
        {access.data.models.length > 0 && <ModelTable models={access.data.models} discovered={[]} prices={pricing} />}
      </div>
    );
  }
  // Keyed by the saved list: a publication elsewhere on this tab replaces the list, a save leaves it as it is.
  return <Editor key={`${company.id}:${access.data.models.join("\n")}`} company={company} readOnly={readOnly} initial={access.data.models} discovered={discovered} prices={pricing} />;
}

/** Why the owner could not save: the two ceiling rules have their own copy; anything else uses the shared table. */
function describeSaveFailure(failure: unknown): string {
  if (failure instanceof ApiError && failure.code === "DISCOVERY_REQUIRED") return NOTHING_DISCOVERED;
  if (failure instanceof ApiError && failure.code === "MODEL_NOT_DISCOVERED") return "One or more selected models are not reachable through this company's keys. Refresh the models and choose from the list.";
  return errorMessage(failure);
}

function ModelTable({ models, discovered, prices, selected, onToggle }: { models: string[]; discovered: string[]; prices: Price[]; selected?: string[]; onToggle?: (id: string, allowed: boolean) => void }) {
  const latest = (id: string) => prices.filter((price) => price.upstream_id === id).sort((a, b) => b.version - a.version)[0];
  const columns: Column<string>[] = [
    ...(onToggle
      ? [{ id: "allowed", header: "Allowed", cell: (id: string) => <input type="checkbox" className="size-5 cursor-pointer accent-action" aria-label={`Allow ${id}`} checked={selected?.includes(id) ?? false} onChange={(event) => onToggle(id, event.target.checked)} /> }]
      : []),
    { id: "model", header: "Model", cell: (id) => <span className="flex flex-wrap items-center gap-2"><span className="break-all font-mono text-body">{id}</span>{discovered.length > 0 && !discovered.includes(id) && <Badge tone="warning">Not reachable</Badge>}</span> },
    { id: "input", header: "Input / 1M tokens", align: "right", cell: (id) => { const price = latest(id); return price ? `$${usd(price.input_micros)}` : <span className="text-muted">No price</span>; } },
    { id: "output", header: "Output / 1M tokens", align: "right", cell: (id) => { const price = latest(id); return price ? `$${usd(price.output_micros)}` : <span className="text-muted">No price</span>; } },
  ];
  return <DataTable caption="Allowed models" columns={columns} rows={models} rowKey={(id) => id} pageSize={50} empty={<EmptyState icon={Layers} title="No models allowed" hint="Until at least one model is allowed, the company cannot publish a catalogue." />} />;
}

function Editor({ company, readOnly, initial, discovered, prices }: { company: Company; readOnly: boolean; initial: string[]; discovered: string[]; prices: Price[] }) {
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const [models, setModels] = useState(initial);
  // Every discovered model, plus any saved one the keys no longer reach (flagged, so the owner can clear it).
  const rows = [...new Set([...discovered, ...initial])].sort();
  const save = useMutation({
    mutationFn: () => platform.setModelAccess(company.id, models),
    onSuccess: (saved) => {
      client.setQueryData(["platform", "company", company.id, "models"], saved);
      void client.invalidateQueries({ queryKey: ["platform", "company", company.id, "catalog"] });
      void client.invalidateQueries({ queryKey: ["platform", "audit"] });
      toast.push({ tone: "success", title: "Allowed models saved" });
    },
  });
  const toggle = (id: string, allowed: boolean) => setModels((current) => (allowed ? (current.includes(id) ? current : [...current, id]) : current.filter((item) => item !== id)));
  const dirty = JSON.stringify([...models].sort()) !== JSON.stringify([...initial].sort());
  return (
    <section className="flex flex-col gap-4">
      <p className="text-body text-muted">The most this company's administrators can publish to their members. Choose among the models the company's keys can reach. A model without a price is metered but costs nothing in reports until you set one under Prices.</p>
      <ModelTable models={readOnly ? initial : rows} discovered={discovered} prices={prices} selected={readOnly ? undefined : models} onToggle={readOnly ? undefined : toggle} />
      {readOnly ? (
        <Alert tone="info">Reactivate the company to change its models.</Alert>
      ) : (
        <>
          <p aria-live="polite" className="text-caption text-muted">{models.length} of {rows.length} allowed</p>
          {save.isError && <Alert tone="destructive">{describeSaveFailure(save.error)}</Alert>}
          <div><Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>Save models</Button></div>
        </>
      )}
    </section>
  );
}
