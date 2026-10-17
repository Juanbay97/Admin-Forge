import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Company } from "../../../api/platform";
import { ApiError } from "../../../api/client";
import { describeBrandingFailure, draftFrom, draftToDocument, type Branding, type Draft } from "../../../brand/branding";
import { useServices } from "../../../shell/services";
import { Alert } from "../../../ui/Alert";
import { Button } from "../../../ui/Button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../../../ui/Card";
import { Skeleton } from "../../../ui/Skeleton";
import { AlertDialog } from "../../../ui/overlay/Dialog";
import { BrandDraftEditor, hasIssues } from "../branding/BrandDraftEditor";

export function BrandingTab({ company, readOnly }: { company: Company; readOnly: boolean }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const query = useQuery({ queryKey: ["platform", "company", company.id, "branding"], queryFn: () => platform.branding(company.id) });
  if (query.isError) return <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void query.refetch()}>{t("common:actions.tryAgain")}</Button>}>{t("companies.brandingTab.loadError")}</Alert>;
  if (!query.data) return <Skeleton className="h-64 w-full" />;
  return <Editor key={company.id} company={company} initial={query.data} readOnly={readOnly} />;
}

function Editor({ company, initial, readOnly }: { company: Company; initial: Branding; readOnly: boolean }) {
  const { t } = useTranslation(["platform", "common"]);
  const { platform } = useServices();
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(initial));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const adopt = (next: Branding) => {
    setSaved(next);
    setDraft(draftFrom(next));
  };
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setFailure(null);
    setConflict(false);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      setFailure(describeBrandingFailure(error));
      setConflict(error instanceof ApiError && error.code === "REVISION_CONFLICT");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <p className="text-body text-muted">{t("companies.brandingTab.intro", { revision: saved.revision })}</p>
      {readOnly && <Alert tone="info">{t("companies.brandingTab.readOnly")}</Alert>}
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>{t("companies.brandingTab.editorTitle")}</CardTitle>
          <CardDescription>{t("companies.brandingTab.editorDescription")}</CardDescription>
        </CardHeader>
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void run(async () => {
              const next = await platform.saveBranding(company.id, saved.revision, draftToDocument(draft));
              adopt(next);
              setNotice(t("companies.brandingTab.saved", { revision: next.revision }));
            });
          }}
        >
          <CardContent className="flex flex-col gap-4">
            <fieldset disabled={readOnly || busy} className="flex flex-col gap-4">
              <BrandDraftEditor draft={draft} saved={saved} busy={busy} onChange={(key, value) => { setDraft((current) => ({ ...current, [key]: value })); setNotice(null); }} />
            </fieldset>
            {failure && <Alert tone="destructive">{failure}</Alert>}
            {notice && <Alert tone="success">{notice}</Alert>}
          </CardContent>
          {!readOnly && (
            <CardFooter className="flex-wrap gap-3">
              <Button type="submit" loading={busy} disabled={hasIssues(draft)}>{t("companies.brandingTab.save")}</Button>
              <Button variant="outline" disabled={busy} onClick={() => setConfirming(true)}>{t("companies.brandingTab.reset")}</Button>
              {conflict && <Button variant="outline" disabled={busy} onClick={() => void run(async () => adopt(await platform.branding(company.id)))}>{t("companies.brandingTab.reload")}</Button>}
            </CardFooter>
          )}
        </form>
      </Card>
      <AlertDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("companies.brandingTab.resetTitle")}
        description={t("companies.brandingTab.resetDescription")}
        confirmLabel={t("companies.brandingTab.resetConfirm")}
        destructive
        onConfirm={() => run(async () => { const next = await platform.resetBranding(company.id, saved.revision); adopt(next); setNotice(t("companies.brandingTab.resetDone", { revision: next.revision })); })}
      />
    </section>
  );
}