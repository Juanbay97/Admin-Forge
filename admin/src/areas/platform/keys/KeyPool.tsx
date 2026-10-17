import { KeyRound, Plus, RefreshCw } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { GatewayKey } from "../../../api/platform";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { DataTable, type Column } from "../../../ui/DataTable";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Input } from "../../../ui/Input";
import { KeyField } from "../../../ui/KeyField";
import { PageHeader } from "../../../ui/PageHeader";
import { Select } from "../../../ui/Select";
import { AlertDialog, Dialog } from "../../../ui/overlay/Dialog";
import { useToast } from "../../../ui/toast/Toast";

const host = (origin: string) => {
  try {
    return new URL(origin).host;
  } catch {
    return origin;
  }
};

export function KeyPool() {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const pool = useQuery({ queryKey: ["platform", "keys"], queryFn: () => platform.keys() });
  const [adding, setAdding] = useState(false);
  const [rotating, setRotating] = useState<GatewayKey | null>(null);
  const [disabling, setDisabling] = useState<GatewayKey | null>(null);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["platform", "keys"] });
    void client.invalidateQueries({ queryKey: ["platform", "audit"] });
  };
  const toggle = useMutation({
    mutationFn: ({ key, enabled }: { key: GatewayKey; enabled: boolean }) => platform.setKeyEnabled(key.id, enabled),
    onSuccess: (key) => { refresh(); toast.push({ tone: "success", title: t(key.status === "active" ? "keys.toast.enabled" : "keys.toast.disabled", { label: key.label }) }); },
    onError: (error) => toast.push({ tone: "destructive", title: t("keys.toast.notChanged"), message: errorMessage(error) }),
  });

  const columns: Column<GatewayKey>[] = [
    { id: "label", header: t("keys.columns.label"), sortValue: (key) => key.label, cell: (key) => <span className="font-medium text-fg">{key.label}</span> },
    { id: "gateway", header: t("keys.columns.gateway"), sortValue: (key) => host(key.origin), cell: (key) => host(key.origin) },
    { id: "key", header: t("keys.columns.key"), cell: (key) => (key.has_key ? <span className="font-mono">••••{key.hint}</span> : <span className="text-muted">{t("keys.noKeyStored")}</span>) },
    { id: "status", header: t("keys.columns.status"), sortValue: (key) => key.status, cell: (key) => <Badge tone={key.status === "active" ? "success" : "neutral"}>{key.status === "active" ? t("keys.status.active") : t("keys.status.disabled")}</Badge> },
    { id: "companies", header: t("keys.columns.companies"), align: "right", sortValue: (key) => key.companies, cell: (key) => key.companies },
    {
      id: "actions",
      header: t("keys.columns.actions"),
      align: "right",
      cell: (key) => (
        <span className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" aria-label={t("keys.rotateAria", { label: key.label })} onClick={() => setRotating(key)}><RefreshCw aria-hidden="true" className="size-4" />{t("keys.rotate")}</Button>
          {key.status === "active" ? (
            <Button size="sm" variant="ghost" aria-label={t("keys.disableAria", { label: key.label })} onClick={() => setDisabling(key)}>{t("keys.disable")}</Button>
          ) : (
            <Button size="sm" variant="ghost" aria-label={t("keys.enableAria", { label: key.label })} loading={toggle.isPending && toggle.variables?.key.id === key.id} onClick={() => toggle.mutate({ key, enabled: true })}>{t("keys.enable")}</Button>
          )}
        </span>
      ),
    },
  ];

  const add = <Button onClick={() => setAdding(true)}><Plus aria-hidden="true" className="size-4" />{t("keys.add")}</Button>;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title={t("keys.title")} description={t("keys.description")} actions={add} />
      {pool.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void pool.refetch()}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(pool.error)}</Alert>}
      <DataTable
        caption={t("keys.title")}
        columns={columns}
        rows={pool.data?.keys ?? []}
        rowKey={(key) => key.id}
        loading={pool.isPending}
        initialSort={{ id: "label", direction: "asc" }}
        empty={<EmptyState icon={KeyRound} title={t("keys.empty.title")} hint={t("keys.empty.hint")} action={add} />}
      />
      <AddKeyDialog open={adding} onOpenChange={setAdding} origins={pool.data?.allowed_origins ?? []} onAdded={(key) => { refresh(); toast.push({ tone: "success", title: t("keys.toast.added", { label: key.label }) }); }} />
      <RotateDialog key={rotating?.id ?? "none"} gatewayKey={rotating} onOpenChange={(open) => !open && setRotating(null)} onRotated={(key) => { refresh(); toast.push({ tone: "success", title: t("keys.toast.rotated", { label: key.label }) }); }} />
      <AlertDialog
        open={disabling !== null}
        onOpenChange={(open) => !open && setDisabling(null)}
        title={t("keys.disableDialog.title", { label: disabling?.label ?? t("keys.keyWord") })}
        description={disabling && disabling.companies > 0 ? t("keys.disableDialog.used", { count: disabling.companies }) : t("keys.disableDialog.unused")}
        confirmLabel={t("keys.disableDialog.confirm")}
        destructive
        onConfirm={async () => { if (disabling) await toggle.mutateAsync({ key: disabling, enabled: false }).catch(() => undefined); }}
      />
    </section>
  );
}

function AddKeyDialog({ open, onOpenChange, origins, onAdded }: { open: boolean; onOpenChange: (open: boolean) => void; origins: string[]; onAdded: (key: GatewayKey) => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const [label, setLabel] = useState("");
  const [origin, setOrigin] = useState("");
  const [secret, setSecret] = useState("");
  const create = useMutation({
    mutationFn: () => platform.createKey({ label: label.trim(), origin: origin || origins[0] || "", key: secret }),
    onSuccess: (key) => { setLabel(""); setOrigin(""); onOpenChange(false); onAdded(key); },
    onSettled: () => setSecret(""), // write-only: the text leaves the page the moment it is submitted, whatever the answer
  });
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) { create.reset(); setSecret(""); } onOpenChange(next); }} title={t("keys.addDialog.title")} description={t("keys.addDialog.description")}>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (label.trim() && secret && !create.isPending) create.mutate();
        }}
      >
        <Field label={t("keys.addDialog.label")} hint={t("keys.addDialog.labelHint")} required>
          {(control) => <Input {...control} value={label} onChange={(event) => setLabel(event.target.value)} autoComplete="off" maxLength={80} />}
        </Field>
        <Field label={t("keys.addDialog.gateway")} required>
          {(control) => (
            <Select {...control} value={origin || origins[0] || ""} onChange={(event) => setOrigin(event.target.value)}>
              {origins.map((value) => <option key={value} value={value}>{value}</option>)}
            </Select>
          )}
        </Field>
        <KeyField label={t("keys.addDialog.apiKey")} value={secret} onValueChange={setSecret} required />
        {create.isError && <Alert tone="destructive">{errorMessage(create.error)}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("common:actions.cancel")}</Button>
          <Button type="submit" loading={create.isPending} disabled={!label.trim() || !secret}>{t("keys.addDialog.submit")}</Button>
        </div>
      </form>
    </Dialog>
  );
}

function RotateDialog({ gatewayKey, onOpenChange, onRotated }: { gatewayKey: GatewayKey | null; onOpenChange: (open: boolean) => void; onRotated: (key: GatewayKey) => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const [secret, setSecret] = useState("");
  const rotate = useMutation({
    mutationFn: () => platform.rotateKey(gatewayKey!.id, gatewayKey!.revision, secret),
    onSuccess: (key) => { onOpenChange(false); onRotated(key); },
    onSettled: () => setSecret(""),
  });
  return (
    <Dialog open={gatewayKey !== null} onOpenChange={(next) => { if (!next) { rotate.reset(); setSecret(""); } onOpenChange(next); }} title={t("keys.rotateDialog.title", { label: gatewayKey?.label ?? t("keys.keyWord") })} description={t("keys.rotateDialog.description")}>
      <form noValidate className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); if (secret && !rotate.isPending) rotate.mutate(); }}>
        <KeyField label={t("keys.rotateDialog.newKey")} value={secret} onValueChange={setSecret} lastFour={gatewayKey?.hint ?? undefined} required />
        {rotate.isError && <Alert tone="destructive">{errorMessage(rotate.error)}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("common:actions.cancel")}</Button>
          <Button type="submit" loading={rotate.isPending} disabled={!secret}>{t("keys.rotateDialog.submit")}</Button>
        </div>
      </form>
    </Dialog>
  );
}