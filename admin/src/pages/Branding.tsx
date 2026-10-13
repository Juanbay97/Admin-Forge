import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import type { Organization } from "../api/account";
import type { BrandingApi } from "../api/branding";
import { ApiError } from "../api/client";
import {
  assetHash,
  describeBrandingFailure,
  draftFrom,
  draftToDocument,
  paletteIssues,
  type AssetKind,
  type Branding as BrandingRecord,
  type Draft,
} from "../brand/branding";
import { generatePalette } from "../brand/palette";
import { BrandPreview, type Mark } from "../components/BrandPreview";
import { ThemeEditor, type Uploads } from "../components/ThemeEditor";
import { Alert } from "../ui/Alert";
import { Button } from "../ui/Button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../ui/Card";
import { PageHeader } from "../ui/PageHeader";
import { AlertDialog } from "../ui/overlay/Dialog";

interface BrandingProps {
  api: BrandingApi;
  organization: Organization;
  /** The saved record the form starts from; replaced through `onChanged` after a save, reset or reload. */
  branding: BrandingRecord;
  onChanged: (branding: BrandingRecord) => void;
}

type CopyState = "idle" | "copied" | "failed";

// The organization's company code: the one thing employees type in the client before they see the branding.
function CompanyCode({ code }: { code: string }) {
  const [copy, setCopy] = useState<CopyState>("idle");
  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  }
  return (
    <Card role="group" aria-label="Company code" className="max-w-2xl">
      <CardHeader>
        <h2 className="font-title text-card font-semibold">Company code</h2>
        <CardDescription>Employees type this code the first time they open the app so it shows your company&apos;s branding.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <code data-testid="company-code" className="select-all rounded-control bg-subtle px-3 py-2 font-mono text-card">
            {code}
          </code>
          <Button variant="outline" onClick={() => void copyCode()}>
            Copy company code
          </Button>
        </div>
        {copy === "copied" && <Alert tone="success">Company code copied.</Alert>}
        {copy === "failed" && <Alert tone="destructive">Could not copy the code. Select it and copy it manually.</Alert>}
      </CardContent>
    </Card>
  );
}
function releaseBitmaps(uploads: Uploads) {
  for (const upload of Object.values(uploads)) upload.bitmap?.close();
}

export function Branding({ api, organization, branding, onChanged }: BrandingProps) {
  const orgId = organization.id;
  const [saved, setSaved] = useState(branding);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(branding));
  const [uploads, setUploads] = useState<Uploads>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [busy, setBusy] = useState(false);

  // Locally decoded logos are released with the page.
  const live = useRef(uploads);
  live.current = uploads;
  useEffect(() => () => releaseBitmaps(live.current), []);

  const { primary, accent, tint, heading, body } = draft;
  const palette = useMemo(() => generatePalette({ primary, accent, tint, heading, body }), [primary, accent, tint, heading, body]);

  const issues = useMemo(() => paletteIssues(draft), [draft]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setNotice(null);
  };

  function adopt(received: BrandingRecord) {
    // Save and reset answers carry no company code; it belongs to the organization, so it is kept.
    const next = received.code === undefined && saved.code !== undefined ? { ...received, code: saved.code } : received;
    releaseBitmaps(uploads);
    setSaved(next);
    setDraft(draftFrom(next));
    setUploads({});
    onChanged(next);
  }

  function markFor(kinds: AssetKind[]): Mark | null {
    for (const kind of kinds) {
      const hash = draft.assets[kind];
      if (!hash) continue;
      const local = uploads[kind]?.bitmap;
      if (local) return { bitmap: local };
      const url = saved.assets[kind];
      if (url && assetHash(url) === hash) return { url };
    }
    return null;
  }

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

  async function upload(kind: AssetKind, file: File) {
    await run(async () => {
      const stored = await api.uploadAsset(orgId, kind, file);
      const bitmap = await createImageBitmap(file).catch(() => undefined);
      setUploads((current) => {
        current[kind]?.bitmap?.close();
        return { ...current, [kind]: { width: stored.width, height: stored.height, bitmap } };
      });
      setDraft((current) => ({ ...current, assets: { ...current.assets, [kind]: stored.sha256 } }));
    });
  }

  function remove(kind: AssetKind) {
    const { [kind]: _removed, ...rest } = draft.assets;
    set("assets", rest);
    setUploads((current) => {
      current[kind]?.bitmap?.close();
      const { [kind]: _gone, ...others } = current;
      return others;
    });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      const next = await api.save(orgId, saved.revision, draftToDocument(draft));
      adopt(next);
      setNotice(`Branding saved (revision ${next.revision}).`);
    });
  }

  async function reset() {
    await run(async () => {
      const next = await api.reset(orgId, saved.revision);
      adopt(next);
      setNotice(`Branding reset to the Prometheon default (revision ${next.revision}).`);
    });
  }

  async function reload() {
    await run(async () => {
      adopt(await api.get(orgId));
    });
  }

  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Branding" description="How Forge looks for your company: name, colors, fonts and logos." />
      <p className="-mt-3 text-body text-muted">Revision {saved.revision}</p>
      {saved.code !== undefined && <CompanyCode code={saved.code} />}
      <Card role="region" aria-label="Brand editor" className="max-w-2xl">
        <CardHeader>
          <CardTitle>Brand editor</CardTitle>
          <CardDescription>The previews below follow every edit; the app itself changes when you save.</CardDescription>
        </CardHeader>
        <form onSubmit={save} noValidate>
          <CardContent className="flex flex-col gap-4">
            <ThemeEditor
              draft={draft}
              issues={issues}
              saved={saved}
              uploads={uploads}
              busy={busy}
              onChange={set}
              onUpload={(kind, file) => void upload(kind, file)}
              onRemove={remove}
            />
            {failure && <Alert tone="destructive">{failure}</Alert>}
            {notice && <Alert tone="success">{notice}</Alert>}
          </CardContent>
          <CardFooter className="flex-wrap gap-3">
            <Button type="submit" loading={busy}>
              Save branding
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => setConfirmingReset(true)}>
              Reset to default
            </Button>
            {conflict && (
              <Button variant="outline" disabled={busy} onClick={() => void reload()}>
                Reload branding
              </Button>
            )}
          </CardFooter>
        </form>
      </Card>
      <AlertDialog
        open={confirmingReset}
        onOpenChange={setConfirmingReset}
        title="Reset branding?"
        description="Reset to the Prometheon default? This publishes a new revision; the history is kept."
        confirmLabel="Confirm reset"
        destructive
        onConfirm={reset}
      />
      <BrandPreview
        palette={palette}
        name={draft.name}
        loginCopy={draft.loginCopy}
        light={markFor(["logoLight", "isotipo"])}
        dark={markFor(["logoDark", "logoLight", "isotipo"])}
        favicon={markFor(["isotipo"])}
      />
    </section>
  );
}