import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { DEFAULT_BRANDING, draftFrom, type Draft } from "../../../../brand/branding";
import { isCompanyCode, slugFromName } from "../../../../platform/companies";
import { errorMessage } from "../../../../shell/errors";
import { useServices } from "../../../../shell/services";
import { Alert } from "../../../../ui/Alert";
import { Button } from "../../../../ui/Button";
import { Checkbox } from "../../../../ui/Choice";
import { Field } from "../../../../ui/Field";
import { useZodForm } from "../../../../ui/form";
import { Input } from "../../../../ui/Input";
import { BrandDraftEditor, hasIssues } from "../../branding/BrandDraftEditor";
import { loadAllCompanies } from "../data";
import { adminSchema, companySchema, type AdminStep, type CompanyStep } from "./schema";

export const defaultDraft = (): Draft => draftFrom(DEFAULT_BRANDING);

function Nav({ onBack, nextLabel, nextDisabled, loading }: { onBack?: () => void; nextLabel?: string; nextDisabled?: boolean; loading?: boolean }) {
  const { t } = useTranslation(["platform", "common"]);
  return (
    <div className="flex justify-between gap-3 pt-2">
      {onBack ? <Button variant="outline" onClick={onBack}>{t("common:actions.back")}</Button> : <span />}
      <Button type="submit" disabled={nextDisabled} loading={loading}>{nextLabel ?? t("wizard.next")}</Button>
    </div>
  );
}

export function CompanyStepForm({ value, onNext }: { value: CompanyStep | null; onNext: (value: CompanyStep) => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const companies = useQuery({ queryKey: ["platform", "companies", "all"], queryFn: () => loadAllCompanies(platform) });
  const form = useZodForm(companySchema, { defaultValues: value ?? { name: "", code: "", department: "General" }, mode: "onChange" });
  const [edited, setEdited] = useState(Boolean(value?.code));
  const { errors } = form.formState;
  const code = form.watch("code");
  const taken = (companies.data ?? []).some((company) => company.slug === code);
  const valid = isCompanyCode(code);
  const name = form.register("name");
  return (
    <form noValidate className="flex flex-col gap-4" onSubmit={form.handleSubmit((values) => { if (!taken) onNext(values); })}>
      <Field label={t("wizard.company.name")} error={errors.name?.message}>
        {(control) => (
          <Input
            {...control}
            {...name}
            autoComplete="off"
            autoFocus
            onChange={(event) => {
              void name.onChange(event);
              if (!edited) form.setValue("code", slugFromName(event.target.value), { shouldValidate: true });
            }}
          />
        )}
      </Field>
      <Field
        label={t("wizard.company.code")}
        hint={t("wizard.company.codeHint")}
        error={errors.code?.message ?? (taken ? t("wizard.company.codeTaken") : undefined)}
      >
        {(control) => <Input {...control} {...form.register("code", { onChange: () => setEdited(true) })} autoComplete="off" spellCheck={false} className="font-mono" />}
      </Field>
      {valid && !taken && companies.isSuccess && <p className="-mt-2 text-caption text-on-ok-soft">{t("wizard.company.codeAvailable")}</p>}
      <Field label={t("wizard.company.department")} hint={t("wizard.company.departmentHint")} error={errors.department?.message}>
        {(control) => <Input {...control} {...form.register("department")} autoComplete="off" />}
      </Field>
      <Nav nextDisabled={taken || !form.formState.isValid} />
    </form>
  );
}

export function BrandingStepForm({ value, onNext, onBack }: { value: Draft | null; onNext: (value: Draft | null) => void; onBack: () => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const [custom, setCustom] = useState(value !== null);
  const [draft, setDraft] = useState<Draft>(value ?? defaultDraft());
  return (
    <form noValidate className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); onNext(custom ? draft : null); }}>
      <Checkbox label={t("wizard.branding.customize")} checked={custom} onCheckedChange={(checked) => setCustom(checked === true)} />
      {!custom && <p className="text-body text-muted">{t("wizard.branding.defaultNote")}</p>}
      {custom && <BrandDraftEditor draft={draft} saved={DEFAULT_BRANDING} onChange={(key, next) => setDraft((current) => ({ ...current, [key]: next }))} />}
      <Nav onBack={onBack} nextDisabled={custom && hasIssues(draft)} />
    </form>
  );
}

export function AdminStepForm({ value, onNext, onBack }: { value: AdminStep | null; onNext: (value: AdminStep) => void; onBack: () => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const form = useZodForm(adminSchema, { defaultValues: value ?? { email: "", name: "" } });
  const { errors } = form.formState;
  return (
    <form noValidate className="flex flex-col gap-4" onSubmit={form.handleSubmit(onNext)}>
      <p className="text-body text-muted">{t("wizard.admin.intro")}</p>
      <Field label={t("wizard.admin.email")} error={errors.email?.message}>
        {(control) => <Input {...control} type="email" autoComplete="off" autoFocus {...form.register("email")} />}
      </Field>
      <Field label={t("wizard.admin.name")} error={errors.name?.message}>
        {(control) => <Input {...control} autoComplete="off" {...form.register("name")} />}
      </Field>
      <Nav onBack={onBack} />
    </form>
  );
}

/**
 * Gateway keys only. The wizard knows nothing about models: the owner chooses them from the models the company's keys can reach
 * when publishing the catalog from the company's Models tab after creation.
 */
export function KeysStepForm({ keys, onNext, onBack }: { keys: string[]; onNext: (keys: string[]) => void; onBack: () => void }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const pool = useQuery({ queryKey: ["platform", "keys"], queryFn: () => platform.keys() });
  const [chosen, setChosen] = useState<string[]>(keys);
  const usable = (pool.data?.keys ?? []).filter((key) => key.status === "active" && key.has_key);

  return (
    <form noValidate className="flex flex-col gap-6" onSubmit={(event) => { event.preventDefault(); if (chosen.length > 0) onNext(chosen); }}>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-body font-medium text-fg">{t("wizard.keys.legend")}</legend>
        <p className="text-body text-muted">{t("wizard.keys.intro")}</p>
        {pool.isPending && <p role="status" className="text-muted">{t("wizard.keys.loading")}</p>}
        {pool.isError && <Alert tone="destructive">{errorMessage(pool.error)}</Alert>}
        {pool.isSuccess && usable.length === 0 && <Alert tone="warning">{t("wizard.keys.none")}</Alert>}
        {usable.map((key) => (
          <Checkbox
            key={key.id}
            label={`${key.label} · ${new URL(key.origin).host} · ••••${key.hint ?? ""}`}
            checked={chosen.includes(key.id)}
            onCheckedChange={(checked) => setChosen((current) => (checked === true ? [...current, key.id] : current.filter((id) => id !== key.id)))}
          />
        ))}
      </fieldset>
      <p className="text-body text-muted">{t("wizard.keys.modelsNote")}</p>
      <Nav onBack={onBack} nextDisabled={chosen.length === 0} />
    </form>
  );
}
