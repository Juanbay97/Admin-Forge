import { Plus, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Company } from "../../../api/platform";
import { usd } from "../../../platform/money";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { Skeleton } from "../../../ui/Skeleton";
import { useToast } from "../../../ui/toast/Toast";
import { Layers } from "lucide-react";

export function ModelsTab({ company, readOnly }: { company: Company; readOnly: boolean }) {
  const { platform } = useServices();
  const access = useQuery({ queryKey: ["platform", "company", company.id, "models"], queryFn: () => platform.modelAccess(company.id) });
  const prices = useQuery({ queryKey: ["platform", "prices"], queryFn: () => platform.prices() });
  if (access.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void access.refetch()}>Try again</Button>}>{errorMessage(access.error)}</Alert>;
  if (!access.data) return <Skeleton className="h-40 w-full" />;
  return <Editor key={company.id} company={company} readOnly={readOnly} initial={access.data.models} prices={prices.data?.prices ?? []} />;
}

function Editor({ company, readOnly, initial, prices }: { company: Company; readOnly: boolean; initial: string[]; prices: Array<{ upstream_id: string; input_micros: number; output_micros: number; version: number }> }) {
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const [models, setModels] = useState(initial);
  const [draft, setDraft] = useState("");
  const latest = (id: string) => prices.filter((price) => price.upstream_id === id).sort((a, b) => b.version - a.version)[0];
  const save = useMutation({
    mutationFn: () => platform.setModelAccess(company.id, models),
    onSuccess: (saved) => {
      client.setQueryData(["platform", "company", company.id, "models"], saved);
      void client.invalidateQueries({ queryKey: ["platform", "audit"] });
      toast.push({ tone: "success", title: "Allowed models saved" });
    },
  });
  const add = () => {
    const clean = draft.trim();
    if (clean && clean.length <= 255 && !models.includes(clean)) setModels([...models, clean]);
    setDraft("");
  };
  const columns: Column<string>[] = [
    { id: "model", header: "Model", cell: (id) => <span className="font-mono text-body">{id}</span> },
    { id: "input", header: "Input / 1M tokens", align: "right", cell: (id) => { const price = latest(id); return price ? `$${usd(price.input_micros)}` : <span className="text-muted">No price</span>; } },
    { id: "output", header: "Output / 1M tokens", align: "right", cell: (id) => { const price = latest(id); return price ? `$${usd(price.output_micros)}` : <span className="text-muted">No price</span>; } },
    ...(readOnly ? [] : [{ id: "remove", header: "Remove", align: "right" as const, cell: (id: string) => <Button variant="ghost" size="icon" aria-label={`Remove ${id}`} onClick={() => setModels(models.filter((item) => item !== id))}><Trash2 aria-hidden="true" className="size-4" /></Button> }]),
  ];
  const dirty = JSON.stringify(models) !== JSON.stringify(initial);
  return (
    <section className="flex flex-col gap-4">
      <p className="text-body text-muted">The most this company's administrators can publish to their members. A model without a price is metered but costs nothing in reports until you set one under Prices.</p>
      <DataTable caption="Allowed models" columns={columns} rows={models} rowKey={(id) => id} pageSize={50} empty={<EmptyState icon={Layers} title="No models allowed" hint="Until at least one model is allowed, the company cannot publish a catalogue." />} />
      {readOnly ? (
        <Alert tone="info">Reactivate the company to change its models.</Alert>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Add a model" className="min-w-0 flex-1 sm:max-w-sm">
              {(control) => <Input {...control} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); add(); } }} autoComplete="off" spellCheck={false} placeholder="e.g. gpt-4o" />}
            </Field>
            <Button variant="outline" aria-label="Add model" disabled={!draft.trim()} onClick={add}><Plus aria-hidden="true" className="size-4" />Add</Button>
          </div>
          {save.isError && <Alert tone="destructive">{errorMessage(save.error)}</Alert>}
          <div><Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>Save models</Button></div>
        </>
      )}
    </section>
  );
}