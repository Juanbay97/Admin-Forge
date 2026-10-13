import { KeyRound, Plus, RefreshCw } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
    onSuccess: (key) => { refresh(); toast.push({ tone: "success", title: `${key.label} ${key.status === "active" ? "enabled" : "disabled"}` }); },
    onError: (error) => toast.push({ tone: "destructive", title: "The key was not changed", message: errorMessage(error) }),
  });

  const columns: Column<GatewayKey>[] = [
    { id: "label", header: "Label", sortValue: (key) => key.label, cell: (key) => <span className="font-medium text-fg">{key.label}</span> },
    { id: "gateway", header: "Gateway", sortValue: (key) => host(key.origin), cell: (key) => host(key.origin) },
    { id: "key", header: "Key", cell: (key) => (key.has_key ? <span className="font-mono">••••{key.hint}</span> : <span className="text-muted">No key stored</span>) },
    { id: "status", header: "Status", sortValue: (key) => key.status, cell: (key) => <Badge tone={key.status === "active" ? "success" : "neutral"}>{key.status === "active" ? "Active" : "Disabled"}</Badge> },
    { id: "companies", header: "Companies", align: "right", sortValue: (key) => key.companies, cell: (key) => key.companies },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (key) => (
        <span className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" aria-label={`Rotate ${key.label}`} onClick={() => setRotating(key)}><RefreshCw aria-hidden="true" className="size-4" />Rotate</Button>
          {key.status === "active" ? (
            <Button size="sm" variant="ghost" aria-label={`Disable ${key.label}`} onClick={() => setDisabling(key)}>Disable</Button>
          ) : (
            <Button size="sm" variant="ghost" aria-label={`Enable ${key.label}`} loading={toggle.isPending && toggle.variables?.key.id === key.id} onClick={() => toggle.mutate({ key, enabled: true })}>Enable</Button>
          )}
        </span>
      ),
    },
  ];

  const add = <Button onClick={() => setAdding(true)}><Plus aria-hidden="true" className="size-4" />Add key</Button>;
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Gateway keys" description="The keys the platform owns. Companies use them through their assignments; nobody else ever sees them." actions={add} />
      {pool.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void pool.refetch()}>Try again</Button>}>{errorMessage(pool.error)}</Alert>}
      <DataTable
        caption="Gateway keys"
        columns={columns}
        rows={pool.data?.keys ?? []}
        rowKey={(key) => key.id}
        loading={pool.isPending}
        initialSort={{ id: "label", direction: "asc" }}
        empty={<EmptyState icon={KeyRound} title="No gateway keys yet" hint="Add the first key so companies can reach the model gateway. The key is stored encrypted and only its last four characters are shown." action={add} />}
      />
      <AddKeyDialog open={adding} onOpenChange={setAdding} origins={pool.data?.allowed_origins ?? []} onAdded={(key) => { refresh(); toast.push({ tone: "success", title: `${key.label} added` }); }} />
      <RotateDialog key={rotating?.id ?? "none"} gatewayKey={rotating} onOpenChange={(open) => !open && setRotating(null)} onRotated={(key) => { refresh(); toast.push({ tone: "success", title: `${key.label} rotated` }); }} />
      <AlertDialog
        open={disabling !== null}
        onOpenChange={(open) => !open && setDisabling(null)}
        title={`Disable ${disabling?.label ?? "key"}?`}
        description={disabling && disabling.companies > 0 ? `${disabling.companies} ${disabling.companies === 1 ? "company uses" : "companies use"} this key. They fall back to their other assigned keys; a company with no other active key loses gateway access.` : "No company uses this key."}
        confirmLabel="Disable key"
        destructive
        onConfirm={async () => { if (disabling) await toggle.mutateAsync({ key: disabling, enabled: false }).catch(() => undefined); }}
      />
    </section>
  );
}

function AddKeyDialog({ open, onOpenChange, origins, onAdded }: { open: boolean; onOpenChange: (open: boolean) => void; origins: string[]; onAdded: (key: GatewayKey) => void }) {
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
    <Dialog open={open} onOpenChange={(next) => { if (!next) { create.reset(); setSecret(""); } onOpenChange(next); }} title="Add a gateway key" description="The key is stored encrypted and never shown again.">
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (label.trim() && secret && !create.isPending) create.mutate();
        }}
      >
        <Field label="Label" hint="A name for the pool, e.g. Primary or Backup." required>
          {(control) => <Input {...control} value={label} onChange={(event) => setLabel(event.target.value)} autoComplete="off" maxLength={80} />}
        </Field>
        <Field label="Gateway" required>
          {(control) => (
            <Select {...control} value={origin || origins[0] || ""} onChange={(event) => setOrigin(event.target.value)}>
              {origins.map((value) => <option key={value} value={value}>{value}</option>)}
            </Select>
          )}
        </Field>
        <KeyField label="API key" value={secret} onValueChange={setSecret} required />
        {create.isError && <Alert tone="destructive">{errorMessage(create.error)}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" loading={create.isPending} disabled={!label.trim() || !secret}>Add key</Button>
        </div>
      </form>
    </Dialog>
  );
}

function RotateDialog({ gatewayKey, onOpenChange, onRotated }: { gatewayKey: GatewayKey | null; onOpenChange: (open: boolean) => void; onRotated: (key: GatewayKey) => void }) {
  const { platform } = useServices();
  const [secret, setSecret] = useState("");
  const rotate = useMutation({
    mutationFn: () => platform.rotateKey(gatewayKey!.id, gatewayKey!.revision, secret),
    onSuccess: (key) => { onOpenChange(false); onRotated(key); },
    onSettled: () => setSecret(""),
  });
  return (
    <Dialog open={gatewayKey !== null} onOpenChange={(next) => { if (!next) { rotate.reset(); setSecret(""); } onOpenChange(next); }} title={`Rotate ${gatewayKey?.label ?? "key"}`} description="Replace the stored key text. Companies keep their assignment.">
      <form noValidate className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); if (secret && !rotate.isPending) rotate.mutate(); }}>
        <KeyField label="New API key" value={secret} onValueChange={setSecret} lastFour={gatewayKey?.hint ?? undefined} required />
        {rotate.isError && <Alert tone="destructive">{errorMessage(rotate.error)}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" loading={rotate.isPending} disabled={!secret}>Rotate key</Button>
        </div>
      </form>
    </Dialog>
  );
}