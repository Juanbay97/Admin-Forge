import { History, Layers, Pencil, Plus } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const prices = useQuery({ queryKey: ["platform", "prices"], queryFn: () => platform.prices() });
  const [editing, setEditing] = useState<PriceForm | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const latest = latestPrices(prices.data?.prices ?? []);

  const columns: Column<Price>[] = [
    { id: "model", header: t("prices.columns.model"), sortValue: (price) => price.upstream_id, cell: (price) => <span className="font-mono">{price.upstream_id}</span> },
    { id: "input", header: t("prices.columns.input"), align: "right", sortValue: (price) => price.input_micros, cell: (price) => `$${usd(price.input_micros)}` },
    { id: "output", header: t("prices.columns.output"), align: "right", sortValue: (price) => price.output_micros, cell: (price) => `$${usd(price.output_micros)}` },
    { id: "from", header: t("prices.columns.from"), sortValue: (price) => price.effective_from, cell: (price) => formatDate(price.effective_from) },
    { id: "version", header: t("prices.columns.version"), cell: (price) => <Badge tone="neutral">{t("prices.versionBadge", { version: price.version })}</Badge> },
    {
      id: "actions",
      header: t("prices.columns.actions"),
      align: "right",
      cell: (price) => (
        <span className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" aria-label={t("prices.editAria", { model: price.upstream_id })} onClick={() => setEditing({ model: price.upstream_id, input: usd(price.input_micros), output: usd(price.output_micros), effective: "" })}><Pencil aria-hidden="true" className="size-4" />{t("prices.edit")}</Button>
          <Button size="sm" variant="ghost" aria-label={t("prices.historyAria", { model: price.upstream_id })} onClick={() => setHistory(price.upstream_id)}><History aria-hidden="true" className="size-4" />{t("prices.history")}</Button>
        </span>
      ),
    },
  ];
  const add = <Button onClick={() => setEditing(blank)}><Plus aria-hidden="true" className="size-4" />{t("prices.add")}</Button>;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title={t("prices.title")} description={t("prices.description")} actions={add} />
      {prices.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void prices.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(prices.error)}</Alert>}
      <DataTable
        caption={t("prices.title")}
        columns={columns}
        rows={latest}
        rowKey={(price) => price.upstream_id}
        loading={prices.isPending}
        initialSort={{ id: "model", direction: "asc" }}
        empty={<EmptyState icon={Layers} title={t("prices.empty.title")} hint={t("prices.empty.hint")} action={add} />}
      />
      <PriceDialog
        form={editing}
        onOpenChange={(open) => !open && setEditing(null)}
        onSaved={(price) => {
          void client.invalidateQueries({ queryKey: ["platform", "prices"] });
          void client.invalidateQueries({ queryKey: ["platform", "audit"] });
          toast.push({ tone: "success", title: t("prices.toast.saved", { model: price.upstream_id, version: price.version }) });
        }}
      />
      <HistorySheet model={history} onClose={() => setHistory(null)} />
    </section>
  );
}

function PriceDialog({ form, onOpenChange, onSaved }: { form: PriceForm | null; onOpenChange: (open: boolean) => void; onSaved: (price: Price) => void }) {
  const { t } = useTranslation(["platform", "common"]);
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
    <Dialog open={form !== null} onOpenChange={onOpenChange} title={known ? t("prices.dialog.editTitle", { model: form.model }) : t("prices.dialog.addTitle")} description={t("prices.dialog.description")}>
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
        <Field label={t("prices.dialog.model")} error={errors.model}>{(control) => <Input {...control} {...field("model")} readOnly={known} autoComplete="off" spellCheck={false} />}</Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("prices.dialog.input")} error={errors.input}>{(control) => <Input {...control} {...field("input")} inputMode="decimal" autoComplete="off" />}</Field>
          <Field label={t("prices.dialog.output")} error={errors.output}>{(control) => <Input {...control} {...field("output")} inputMode="decimal" autoComplete="off" />}</Field>
        </div>
        <Field label={t("prices.dialog.effective")} hint={t("prices.dialog.effectiveHint")} error={errors.effective}>{(control) => <Input {...control} {...field("effective")} type="date" />}</Field>
        {save.isError && <Alert tone="destructive">{errorMessage(save.error)}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("common:actions.cancel")}</Button>
          <Button type="submit" loading={save.isPending}>{t("prices.dialog.submit")}</Button>
        </div>
      </form>
    </Dialog>
  );
}

function HistorySheet({ model, onClose }: { model: string | null; onClose: () => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const versions = useQuery({ queryKey: ["platform", "prices", model], queryFn: () => platform.prices(model ?? undefined), enabled: model !== null });
  const rows = [...(versions.data?.prices ?? [])].sort((a, b) => b.version - a.version);
  return (
    <Sheet open={model !== null} onOpenChange={(open) => !open && onClose()} title={t("prices.historySheet.title", { model: model ?? "" })}>
      {versions.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : versions.isError ? (
        <Alert tone="destructive">{errorMessage(versions.error)}</Alert>
      ) : (
        <table className="w-full text-left text-body">
          <caption className="sr-only">{t("prices.historySheet.caption", { model })}</caption>
          <thead><tr className="text-muted"><th scope="col" className="py-2">{t("prices.historySheet.version")}</th><th scope="col">{t("prices.historySheet.input")}</th><th scope="col">{t("prices.historySheet.output")}</th><th scope="col">{t("prices.historySheet.from")}</th></tr></thead>
          <tbody>
            {rows.map((price) => (
              <tr key={price.id} className="border-t border-line"><th scope="row" className="py-2 font-medium">{t("prices.versionBadge", { version: price.version })}</th><td>${usd(price.input_micros)}</td><td>${usd(price.output_micros)}</td><td>{formatDate(price.effective_from)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </Sheet>
  );
}