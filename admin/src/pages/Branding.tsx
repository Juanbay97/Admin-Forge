import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import type { Organization } from "../api/account";
import type { BrandingApi } from "../api/branding";
import { ApiError } from "../api/client";
import {
  ASSET_KINDS,
  assetHash,
  describeBrandingFailure,
  draftFrom,
  draftToDocument,
  paletteIssues,
  type AssetKind,
  type Branding as BrandingRecord,
  type Draft,
} from "../brand/branding";
import { FONT_FAMILIES, FONT_IDS, generatePalette, type FontId } from "../brand/palette";
import { BrandPreview, type Mark } from "../components/BrandPreview";

interface BrandingProps {
  api: BrandingApi;
  organization: Organization;
  /** The saved record the form starts from; replaced through `onChanged` after a save, reset or reload. */
  branding: BrandingRecord;
  onChanged: (branding: BrandingRecord) => void;
}

const FIELD = "rounded border border-carbon/40 px-3 py-2 text-base";
const PRIMARY_BUTTON = "rounded bg-teal px-4 py-2 font-medium text-white transition-colors hover:bg-primary disabled:opacity-60";
const SECONDARY_BUTTON =
  "rounded border border-teal px-4 py-2 text-teal transition-colors hover:bg-teal hover:text-white disabled:opacity-60";

const ASSET_LABELS: Record<AssetKind, string> = {
  logoLight: "Logo for light backgrounds",
  logoDark: "Logo for dark backgrounds",
  isotipo: "Isotipo (square mark)",
};

interface Uploaded {
  width: number;
  height: number;
  bitmap?: ImageBitmap;
}

type Uploads = Partial<Record<AssetKind, Uploaded>>;

interface ColorFieldProps {
  label: string;
  value: string;
  /** Key of the live readability message for this field; the message is shown beside the input. */
  issueKey: string;
  issue?: string;
  onChange: (value: string) => void;
}

function ColorField({ label, value, issueKey, issue, onChange }: ColorFieldProps) {
  const id = `brand-${label.toLowerCase().replace(/\W+/g, "-")}`;
  const valid = /^#[0-9A-Fa-f]{6}$/.test(value);
  return (
    <div className="flex flex-col gap-1 text-sm font-medium">
      <label htmlFor={id}>{label}</label>
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="text"
          value={value}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={issue ? true : undefined}
          aria-describedby={issue ? `${id}-issue` : undefined}
          onChange={(event) => onChange(event.target.value)}
          className={`${FIELD} w-32 font-mono`}
        />
        <input
          type="color"
          aria-label={`Pick ${label.toLowerCase()}`}
          value={valid ? value.toLowerCase() : "#000000"}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="h-10 w-12 cursor-pointer rounded border border-carbon/40 bg-white p-1"
        />
      </div>
      {issue && (
        <p id={`${id}-issue`} data-testid={`issue-${issueKey}`} className="max-w-xs text-xs font-normal text-red-800">
          {issue}
        </p>
      )}
    </div>
  );
}

function FontField({ label, value, onChange }: { label: string; value: FontId; onChange: (value: FontId) => void }) {
  const id = label.toLowerCase().replace(/\W+/g, "-");
  return (
    <div className="flex flex-col gap-1 text-sm font-medium">
      <label htmlFor={`brand-${id}`}>{label}</label>
      <select id={`brand-${id}`} value={value} onChange={(event) => onChange(event.target.value as FontId)} className={FIELD}>
        {FONT_IDS.map((font) => (
          <option key={font} value={font}>
            {FONT_FAMILIES[font]}
          </option>
        ))}
      </select>
    </div>
  );
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
    <div role="group" aria-label="Company code" className="flex max-w-2xl flex-col gap-2 rounded-lg bg-white p-6 shadow">
      <h2 className="text-sm font-medium">Company code</h2>
      <div className="flex flex-wrap items-center gap-3">
        <code data-testid="company-code" className="select-all rounded bg-sand px-3 py-2 font-mono text-lg">
          {code}
        </code>
        <button type="button" onClick={() => void copyCode()} className={SECONDARY_BUTTON}>
          Copy company code
        </button>
      </div>
      <p className="text-sm">Employees type this code the first time they open the app so it shows your company&apos;s branding.</p>
      {copy === "copied" && <p role="status">Company code copied.</p>}
      {copy === "failed" && (
        <p role="alert" className="text-sm font-medium text-red-800">
          Could not copy the code. Select it and copy it manually.
        </p>
      )}
    </div>
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
    setConfirmingReset(false);
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
      <h1 className="font-title text-2xl font-bold text-primary">Branding</h1>
      <p>Revision {saved.revision}</p>
      {saved.code !== undefined && <CompanyCode code={saved.code} />}
      <form onSubmit={save} className="flex max-w-2xl flex-col gap-4 rounded-lg bg-white p-6 shadow">
        <div className="flex flex-col gap-1 text-sm font-medium">
          <label htmlFor="brand-name">Product name</label>
          <input
            id="brand-name"
            type="text"
            value={draft.name}
            autoComplete="off"
            onChange={(event) => set("name", event.target.value)}
            className={FIELD}
          />
        </div>
        <div className="flex flex-col gap-1 text-sm font-medium">
          <label htmlFor="brand-login-message">Login message</label>
          <textarea
            id="brand-login-message"
            value={draft.loginCopy}
            rows={2}
            onChange={(event) => set("loginCopy", event.target.value)}
            className={FIELD}
          />
        </div>
        <div className="flex flex-wrap gap-4">
          <ColorField label="Primary color" issueKey="primary" issue={issues.primary} value={draft.primary} onChange={(value) => set("primary", value)} />
          <ColorField label="Accent color" issueKey="accent" issue={issues.accent} value={draft.accent} onChange={(value) => set("accent", value)} />
          <ColorField label="Background tint" issueKey="tint" issue={issues.tint} value={draft.tint} onChange={(value) => set("tint", value)} />
        </div>
        {issues.combination && (
          <p data-testid="issue-combination" className="text-xs text-red-800">
            {issues.combination}
          </p>
        )}
        <div className="flex flex-wrap gap-4">
          <FontField label="Heading font" value={draft.heading} onChange={(value) => set("heading", value)} />
          <FontField label="Body font" value={draft.body} onChange={(value) => set("body", value)} />
        </div>
        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-medium">Logos (PNG or WebP, up to 256 KB)</legend>
          {ASSET_KINDS.map((kind) => {
            const hash = draft.assets[kind];
            const pending = uploads[kind];
            const published = saved.assets[kind] !== undefined && hash === assetHash(saved.assets[kind]!);
            const id = `brand-asset-${kind}`;
            return (
              <div key={kind} className="flex flex-col gap-1 text-sm font-medium">
                <label htmlFor={id}>{ASSET_LABELS[kind]}</label>
                <input
                  id={id}
                  type="file"
                  accept="image/png,image/webp"
                  disabled={busy}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) void upload(kind, file);
                  }}
                />
                {pending && (
                  <span className="font-normal">
                    Uploaded {pending.width}×{pending.height} px. It goes live when you save.
                  </span>
                )}
                {!pending && published && <span className="font-normal">The current logo is published.</span>}
                {hash && (
                  <button
                    type="button"
                    aria-label={`Remove ${ASSET_LABELS[kind].toLowerCase()}`}
                    onClick={() => remove(kind)}
                    className="self-start rounded border border-carbon/40 px-3 py-1 font-normal transition-colors hover:bg-sand"
                  >
                    Remove
                  </button>
                )}
              </div>
            );
          })}
        </fieldset>
        {failure && (
          <p role="alert" className="text-sm font-medium text-red-800">
            {failure}
          </p>
        )}
        {notice && <p role="status">{notice}</p>}
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
            Save branding
          </button>
          <button type="button" disabled={busy} onClick={() => setConfirmingReset(true)} className={SECONDARY_BUTTON}>
            Reset to default
          </button>
          {conflict && (
            <button type="button" disabled={busy} onClick={() => void reload()} className={SECONDARY_BUTTON}>
              Reload branding
            </button>
          )}
        </div>
        {confirmingReset && (
          <div role="group" aria-label="Confirm reset" className="flex flex-col gap-3 rounded border border-carbon/40 p-4">
            <p className="font-medium">Reset to the Prometheon default? This publishes a new revision; the history is kept.</p>
            <div className="flex gap-3">
              <button type="button" onClick={() => void reset()} className={PRIMARY_BUTTON}>
                Confirm reset
              </button>
              <button type="button" onClick={() => setConfirmingReset(false)} className={SECONDARY_BUTTON}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </form>
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
