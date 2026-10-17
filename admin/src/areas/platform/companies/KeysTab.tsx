import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Company } from "../../../api/platform";
import { addKey, move, removeKey, toEntries, usableCount, type Assigned } from "../../../platform/assignments";
import { errorMessage } from "../../../shell/errors";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Badge } from "../../../ui/Badge";
import { Button } from "../../../ui/Button";
import { Switch } from "../../../ui/Choice";
import { EmptyState } from "../../../ui/EmptyState";
import { Field } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { Skeleton } from "../../../ui/Skeleton";
import { AlertDialog } from "../../../ui/overlay/Dialog";
import { useToast } from "../../../ui/toast/Toast";
import { KeyRound } from "lucide-react";

export function KeysTab({ company, readOnly }: { company: Company; readOnly: boolean }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const assigned = useQuery({ queryKey: ["platform", "company", company.id, "keys"], queryFn: () => platform.companyKeys(company.id) });
  const pool = useQuery({ queryKey: ["platform", "keys"], queryFn: () => platform.keys() });
  if (assigned.isError || pool.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => { void assigned.refetch(); void pool.refetch(); }}>{t("common:actions.tryAgain")}</Button>}>{errorMessage(assigned.error ?? pool.error)}</Alert>;
  if (!assigned.data || !pool.data) return <Skeleton className="h-40 w-full" />;
  return <Editor key={company.id} company={company} readOnly={readOnly} initial={assigned.data.keys.map((item) => ({ key_id: item.key_id, priority: item.priority, active: item.active }))} pool={pool.data.keys} />;
}

function Editor({ company, readOnly, initial, pool }: { company: Company; readOnly: boolean; initial: Assigned[]; pool: Array<{ id: string; label: string; origin: string; hint: string | null; status: string; has_key: boolean }> }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const client = useQueryClient();
  const toast = useToast();
  const [list, setList] = useState<Assigned[]>(initial);
  const [adding, setAdding] = useState("");
  const [removing, setRemoving] = useState<string | null>(null);
  const info = (id: string) => pool.find((key) => key.id === id);
  const available = pool.filter((key) => key.status === "active" && key.has_key && !list.some((item) => item.key_id === key.id));
  const dirty = JSON.stringify(toEntries(list)) !== JSON.stringify(toEntries(initial)) || JSON.stringify(list.map((item) => item.active)) !== JSON.stringify(initial.map((item) => item.active));
  const save = useMutation({
    mutationFn: () => platform.assignKeys(company.id, toEntries(list)),
    onSuccess: (saved) => {
      client.setQueryData(["platform", "company", company.id, "keys"], saved);
      void client.invalidateQueries({ queryKey: ["platform", "audit"] });
      toast.push({ tone: "success", title: t("companies.keysTab.saved") });
    },
  });
  const label = (id: string) => info(id)?.label ?? t("companies.keysTab.unknownKey");
  const hint = (id: string) => `••••${info(id)?.hint ?? ""}`;

  return (
    <section className="flex flex-col gap-4">
      <p className="text-body text-muted">{t("companies.keysTab.intro")}</p>
      {list.length === 0 ? (
        <EmptyState icon={KeyRound} title={t("companies.keysTab.emptyTitle")} hint={t("companies.keysTab.emptyHint")} />
      ) : (
        <ul aria-label={t("companies.keysTab.assigned")} className="divide-y divide-line rounded-card border border-line bg-surface">
          {list.map((item, index) => (
            <li key={item.key_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="w-6 text-caption text-muted" aria-hidden="true">{index + 1}</span>
              <span className="flex min-w-0 flex-col">
                <span className="font-medium text-fg">{label(item.key_id)}</span>
                <span className="text-caption text-muted">{hint(item.key_id)}</span>
              </span>
              {info(item.key_id)?.status !== "active" && <Badge tone="warning">{t("companies.keysTab.disabledInPool")}</Badge>}
              {!readOnly && (
                <span className="ml-auto flex flex-wrap items-center gap-2">
                  <Switch label={<><span className="sr-only">{label(item.key_id)} </span><span>{t("companies.keysTab.activeSwitch")}</span></>} checked={item.active} onCheckedChange={(checked) => setList((current) => current.map((row) => (row.key_id === item.key_id ? { ...row, active: checked } : row)))} />
                  <Button variant="ghost" size="icon" aria-label={t("companies.keysTab.moveUp", { label: label(item.key_id) })} disabled={index === 0} onClick={() => setList(move(list, item.key_id, -1))}><ArrowUp aria-hidden="true" className="size-4" /></Button>
                  <Button variant="ghost" size="icon" aria-label={t("companies.keysTab.moveDown", { label: label(item.key_id) })} disabled={index === list.length - 1} onClick={() => setList(move(list, item.key_id, 1))}><ArrowDown aria-hidden="true" className="size-4" /></Button>
                  <Button variant="ghost" size="icon" aria-label={t("companies.keysTab.removeAria", { label: label(item.key_id) })} onClick={() => setRemoving(item.key_id)}><Trash2 aria-hidden="true" className="size-4" /></Button>
                </span>
              )}
              {readOnly && <Badge tone={item.active ? "success" : "neutral"} className="ml-auto">{item.active ? t("companies.keysTab.on") : t("companies.keysTab.off")}</Badge>}
            </li>
          ))}
        </ul>
      )}
      {readOnly ? (
        <Alert tone="info">{t("companies.keysTab.readOnly")}</Alert>
      ) : (
        <>
          {usableCount(list) === 0 && list.length > 0 && <Alert tone="warning">{t("companies.keysTab.noneActive")}</Alert>}
          <div className="flex flex-wrap items-end gap-3">
            <Field label={t("companies.keysTab.addField")} className="min-w-0 flex-1 sm:max-w-sm">
              {(control) => (
                <Select {...control} value={adding} onChange={(event) => setAdding(event.target.value)}>
                  <option value="">{available.length === 0 ? t("companies.keysTab.noMore") : t("companies.keysTab.choose")}</option>
                  {available.map((key) => <option key={key.id} value={key.id}>{`${key.label} · ••••${key.hint ?? ""}`}</option>)}
                </Select>
              )}
            </Field>
            <Button variant="outline" disabled={!adding} onClick={() => { setList(addKey(list, adding)); setAdding(""); }}><Plus aria-hidden="true" className="size-4" />{t("companies.keysTab.addButton")}</Button>
          </div>
          {save.isError && <Alert tone="destructive">{errorMessage(save.error)}</Alert>}
          <div><Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>{t("companies.keysTab.save")}</Button></div>
        </>
      )}
      <AlertDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t("companies.keysTab.removeTitle", { label: removing ? label(removing) : t("keys.keyWord") })}
        description={list.length === 1 ? t("companies.keysTab.removeLast") : t("companies.keysTab.removeOther")}
        confirmLabel={t("companies.keysTab.removeConfirm")}
        destructive
        onConfirm={() => { if (removing) setList(removeKey(list, removing)); }}
      />
    </section>
  );
}