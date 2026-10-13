import type { Branding as BrandingRecord, AssetKind, Draft } from "../brand/branding";
import { ASSET_KINDS, assetHash, type paletteIssues } from "../brand/branding";
import { FONT_FAMILIES, FONT_IDS, type FontId } from "../brand/palette";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { Input, Textarea } from "../ui/Input";
import { Label } from "../ui/Label";
import { Select } from "../ui/Select";

export const ASSET_LABELS: Record<AssetKind, string> = {
  logoLight: "Logo for light backgrounds",
  logoDark: "Logo for dark backgrounds",
  isotipo: "Isotipo (square mark)",
};

export interface Uploaded {
  width: number;
  height: number;
  bitmap?: ImageBitmap;
}
export type Uploads = Partial<Record<AssetKind, Uploaded>>;

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
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          value={value}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={issue ? true : undefined}
          aria-describedby={issue ? `${id}-issue` : undefined}
          onChange={(event) => onChange(event.target.value)}
          className="w-32 font-mono"
        />
        <input
          type="color"
          aria-label={`Pick ${label.toLowerCase()}`}
          value={valid ? value.toLowerCase() : "#000000"}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="h-10 w-12 cursor-pointer rounded-control border border-line-strong bg-surface p-1 outline-focus focus-visible:outline-2 max-sm:min-h-11"
        />
      </div>
      {issue && (
        <p id={`${id}-issue`} data-testid={`issue-${issueKey}`} className="max-w-xs text-caption font-medium text-danger">
          {issue}
        </p>
      )}
    </div>
  );
}

function FontField({ label, value, onChange }: { label: string; value: FontId; onChange: (value: FontId) => void }) {
  const id = `brand-${label.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select id={id} value={value} onChange={(event) => onChange(event.target.value as FontId)}>
        {FONT_IDS.map((font) => (
          <option key={font} value={font}>
            {FONT_FAMILIES[font]}
          </option>
        ))}
      </Select>
    </div>
  );
}

interface ThemeEditorProps {
  draft: Draft;
  issues: ReturnType<typeof paletteIssues>;
  /** The saved record, to tell which logo is the published one. */
  saved: BrandingRecord;
  uploads: Uploads;
  busy: boolean;
  onChange: <K extends keyof Draft>(key: K, value: Draft[K]) => void;
  onUpload: (kind: AssetKind, file: File) => void;
  onRemove: (kind: AssetKind) => void;
}

/** The fields of a brand theme: name, login message, three colours, two fonts and the three logos. Reusable by the setup wizard. */
export function ThemeEditor({ draft, issues, saved, uploads, busy, onChange, onUpload, onRemove }: ThemeEditorProps) {
  return (
    <>
      <Field label="Product name">
        {(control) => <Input autoComplete="off" value={draft.name} onChange={(event) => onChange("name", event.target.value)} {...control} />}
      </Field>
      <Field label="Login message">
        {(control) => <Textarea rows={2} value={draft.loginCopy} onChange={(event) => onChange("loginCopy", event.target.value)} {...control} />}
      </Field>
      <div className="flex flex-wrap gap-4">
        <ColorField label="Primary color" issueKey="primary" issue={issues.primary} value={draft.primary} onChange={(value) => onChange("primary", value)} />
        <ColorField label="Accent color" issueKey="accent" issue={issues.accent} value={draft.accent} onChange={(value) => onChange("accent", value)} />
        <ColorField label="Background tint" issueKey="tint" issue={issues.tint} value={draft.tint} onChange={(value) => onChange("tint", value)} />
      </div>
      {issues.combination && (
        <p data-testid="issue-combination" className="text-caption font-medium text-danger">
          {issues.combination}
        </p>
      )}
      <div className="flex flex-wrap gap-4">
        <FontField label="Heading font" value={draft.heading} onChange={(value) => onChange("heading", value)} />
        <FontField label="Body font" value={draft.body} onChange={(value) => onChange("body", value)} />
      </div>
      <fieldset className="flex min-w-0 flex-col gap-4">
        <legend className="mb-1 text-body font-medium text-fg">Logos (PNG or WebP, up to 256 KB)</legend>
        {ASSET_KINDS.map((kind) => {
          const hash = draft.assets[kind];
          const pending = uploads[kind];
          const published = saved.assets[kind] !== undefined && hash === assetHash(saved.assets[kind]!);
          const id = `brand-asset-${kind}`;
          return (
            <div key={kind} className="flex flex-col gap-1.5">
              <Label htmlFor={id}>{ASSET_LABELS[kind]}</Label>
              <input
                id={id}
                type="file"
                accept="image/png,image/webp"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) onUpload(kind, file);
                }}
                className="w-full min-w-0 max-w-full text-body file:mr-3 file:min-h-10 file:cursor-pointer file:rounded-control file:border file:border-line-strong file:bg-surface file:px-3 file:text-body file:font-medium file:text-fg hover:file:bg-subtle"
              />
              {pending && (
                <span className="text-caption text-muted">
                  Uploaded {pending.width}×{pending.height} px. It goes live when you save.
                </span>
              )}
              {!pending && published && <span className="text-caption text-muted">The current logo is published.</span>}
              {hash && (
                <Button variant="outline" size="sm" aria-label={`Remove ${ASSET_LABELS[kind].toLowerCase()}`} onClick={() => onRemove(kind)} className="self-start">
                  Remove
                </Button>
              )}
            </div>
          );
        })}
      </fieldset>
    </>
  );
}