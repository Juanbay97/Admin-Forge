import { useMemo } from "react";
import { paletteIssues, type Branding, type Draft } from "../../../brand/branding";
import { generatePalette } from "../../../brand/palette";
import { BrandPreview } from "../../../components/BrandPreview";
import { ThemeEditor } from "../../../components/ThemeEditor";

/** The theme fields plus the live preview, without logo upload (the platform API has none). Controlled: the caller owns the draft. */
export function BrandDraftEditor({ draft, saved, busy = false, onChange }: { draft: Draft; saved: Branding; busy?: boolean; onChange: <K extends keyof Draft>(key: K, value: Draft[K]) => void }) {
  const issues = useMemo(() => paletteIssues(draft), [draft]);
  const { primary, accent, tint, heading, body } = draft;
  const palette = useMemo(() => generatePalette({ primary, accent, tint, heading, body }), [primary, accent, tint, heading, body]);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <ThemeEditor draft={draft} issues={issues} saved={saved} uploads={{}} busy={busy} onChange={onChange} onUpload={() => undefined} onRemove={() => undefined} logos={false} />
      </div>
      <BrandPreview palette={palette} name={draft.name} loginCopy={draft.loginCopy} light={null} dark={null} favicon={null} />
    </div>
  );
}

export const hasIssues = (draft: Draft): boolean => Object.keys(paletteIssues(draft)).length > 0;