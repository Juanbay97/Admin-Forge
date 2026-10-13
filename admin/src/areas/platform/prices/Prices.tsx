import { History, Layers, Pencil, Plus } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Price } from "../../../api/platform";
import { formatDate } from "../../../lib/format";
import { usd } from "../../../platform/money";
import { buildPriceRequest, latestPrices, type PriceForm } from "../../../platform/prices";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { PageHeader } from "../../../ui/PageHeader";
import { Skeleton } from "../../../ui/Skeleton";
import { Dialog, Sheet } from "../../../ui/overlay/Dialog";
import { useToast } from "../../../ui/toast/Toast";

const blank: PriceForm = { model: "", input: "", output: "", effective: "" };

export function Prices() {
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const prices = useQuery({ queryKey: ["platform", "prices"], queryFn: () => platform.prices() });
  const [editing, setEditing] = useState<PriceForm | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const latest = latestPrices(prices.data?.prices ?? []);

  const columns: Column<Price>[] = [
    { id: "model", header: "Model", sortValue: (price) => price.upstream_id, cell: (price) => <span className="font-mono">{price.upstream_id}</span> },
    { id: "input", header: "Input / 1M tokens", align: "right", sortValue: (price) => price.input_micros, cell: (price) => `$${usd(price.input_micros)}` },
    { id: "output", header: "Output / 1M tokens", align: "right", sortValue: (price) => price.output_micros, cell: (price) => `$${usd(price.output_micros)}` },
    { id: "from", header: "Effective from", sortValue: (price) => price.effective_from, cell: (price) => formatDate(price.effective_from) },
    { id: "version", header: "Version", cell: (price) => <Badge tone="neutral">v{price.version}</Badge> },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (price) => (
        <span className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" aria-label={`Edit ${price.upstream_id}`} onClick={() => setEditing({ model: price.upstream_id, input: usd(price.input_micros), output: usd(price.output_micros), effective: "" })}><Pencil aria-hidden="true" className="size-4" />Edit</Button>
          <Button size="sm" variant="ghost" aria-label={`History ${price.upstream_id}`} onClick={() => setHistory(price.upstream_id)}><History aria-hidden="true" className="size-4" />History</Button>
        </span>
      ),
    },
  ];
  const add = <Button onClick={() => setEditing(blank)}><Plus aria-hidden="true" className="size-4" />Add price</Button>;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Model prices" description="What a million tokens cost, per model. Usage reports use the price in force when the request was made; an edit adds a new version and never rewrites history." actions={add} />
      {prices.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void prices.refetch()}>Try again</Button>}>{errorMessage(prices.error)}</Alert>}
      <DataTable
        caption="Model prices"
        columns={columns}
        rows={latest}
        rowKey={(price) => price.upstream_id}
        loading={prices.isPending}
        initialSort={{ id: "model", direction: "asc" }}
        empty={<EmptyState icon={Layers} title="No prices yet" hint="Without a price, requests are metered but their cost reads as zero. Add the models your companies use." action={add} />}
      />
      <PriceDialog
        form={editing}
        onOpenChange={(open) => !open && setEditing(null)}
        onSaved={(price) => {
          void client.invalidateQueries({ queryKey: ["platform", "prices"] });
          void client.invalidateQueries({ queryKey: ["platform", "audit"] });
          toast.push({ tone: "success", title: `Price saved for ${price.upstream_id} (v${price.version})` });
        }}
      />
      <HistorySheet model={history} onClose={() => setHistory(null)} />
    </section>
  );
}

function PriceDialog({ form, onOpenChange, onSaved }: { form: PriceForm | null; onOpenChange: (open: boolean) => void; onSaved: (price: Price) => void }) {
  const { platform } = useServices();
  const [values, setValues] = useState<PriceForm>(blank);
  const [errors, setErrors] = useState<Partial<Record<keyof PriceForm, string>>>({});
  const save = useMutation({ mutationFn: (request: Parameters<typeof platform.setPrice>[0]) => platform.setPrice(request), onSuccess: (price) => { onOpenChange(false); onSaved(price); } });
  const [seen, setSeen] = useState<PriceForm | null>(null);
  if (form !== seen) {
    setSeen(form);
    if (form) {
      setValues(form);
      setErrors({});
      save.reset();
    }
  }
  const field = (key: keyof PriceForm) => ({ value: values[key], onChange: (event: React.ChangeEvent<HTMLInputElement>) => setValues((current) => ({ ...current, [key]: event.target.value })) });
  const known = form !== null && form.model !== "";
  return (
    <Dialog open={form !== null} onOpenChange={onOpenChange} title={known ? `Edit ${form.model}` : "Add a model price"} description="Amounts are US dollars per one million tokens, up to six decimals.">
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          const result = buildPriceRequest(values);
          if (!result.ok) return setErrors(result.errors);
          setErrors({});
          save.mutate(result.request);
        }}
      >
        <Field label="Model" error={errors.model}>{(control) => <Input {...control} {...field("model")} readOnly={known} autoComplete="off" spellCheck={false} />}</Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Input, USD per 1M tokens" error={errors.input}>{(control) => <Input {...control} {...field("input")} inputMode="decimal" autoComplete="off" />}</Field>
          <Field label="Output, USD per 1M tokens" error={errors.output}>{(control) => <Input {...control} {...field("output")} inputMode="decimal" autoComplete="off" />}</Field>
        </div>
        <Field label="Effective from" hint="Leave empty to apply now. A future date schedules the change." error={errors.effective}>{(control) => <Input {...control} {...field("effective")} type="date" />}</Field>
        {save.isError && <Alert tone="destructive">{errorMessage(save.error)}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" loading={save.isPending}>Save price</Button>
        </div>
      </form>
    </Dialog>
  );
}

function HistorySheet({ model, onClose }: { model: string | null; onClose: () => void }) {
  const { platform } = useServices();
  const versions = useQuery({ queryKey: ["platform", "prices", model], queryFn: () => platform.prices(model ?? undefined), enabled: model !== null });
  const rows = [...(versions.data?.prices ?? [])].sort((a, b) => b.version - a.version);
  return (
    <Sheet open={model !== null} onOpenChange={(open) => !open && onClose()} title={`Price history · ${model ?? ""}`}>
      {versions.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : versions.isError ? (
        <Alert tone="destructive">{errorMessage(versions.error)}</Alert>
      ) : (
        <table className="w-full text-left text-body">
          <caption className="sr-only">Versions of {model}</caption>
          <thead><tr className="text-muted"><th scope="col" className="py-2">Version</th><th scope="col">Input</th><th scope="col">Output</th><th scope="col">From</th></tr></thead>
          <tbody>
            {rows.map((price) => (
              <tr key={price.id} className="border-t border-line"><th scope="row" className="py-2 font-medium">v{price.version}</th><td>${usd(price.input_micros)}</td><td>${usd(price.output_micros)}</td><td>{formatDate(price.effective_from)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </Sheet>
  );
}