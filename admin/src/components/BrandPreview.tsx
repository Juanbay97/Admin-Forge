import { useEffect, useLayoutEffect, useRef } from "react";
import { applyVariables } from "../brand/applier";
import type { Palette, TokenMap } from "../brand/palette";

/** A logo to draw: a published same-origin URL, or a locally decoded image that is not published yet. */
export interface Mark {
  url?: string;
  bitmap?: ImageBitmap;
}

interface BrandPreviewProps {
  /** Null when the colors cannot yield a readable theme. */
  palette: Palette | null;
  name: string;
  loginCopy: string;
  light: Mark | null;
  dark: Mark | null;
}

// A decoded bitmap is drawn on a canvas: the admin CSP (`img-src 'self'`) forbids blob: and data: URLs.
function LogoCanvas({ bitmap }: { bitmap: ImageBitmap }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0);
  }, [bitmap]);
  return <canvas ref={ref} role="img" aria-label="Logo preview" className="h-8 w-auto" />;
}

function MarkImage({ mark }: { mark: Mark | null }) {
  if (mark?.bitmap) return <LogoCanvas bitmap={mark.bitmap} />;
  if (mark?.url) return <img src={mark.url} alt="" className="h-8 w-auto" />;
  return null;
}

interface PaneProps {
  label: string;
  tokens: TokenMap;
  fonts: TokenMap;
  mark: Mark | null;
  name: string;
  loginCopy: string;
}

// The pane is an isolated container: the palette tokens are set on this element only (the same CSSOM
// applier as the shell), so nothing outside it changes until the branding is saved.
function Pane({ label, tokens, fonts, mark, name, loginCopy }: PaneProps) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (ref.current) applyVariables(ref.current, { ...tokens, ...fonts });
  }, [tokens, fonts]);
  return (
    <div
      ref={ref}
      role="group"
      aria-label={label}
      className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-(color:--border-heavy) bg-(color:--surface-primary) font-(family-name:--font-body) text-(color:--text-primary)"
    >
      <div className="flex items-center gap-2 border-b border-(color:--border-default) bg-(color:--sidebar-bg) px-3 py-2">
        <MarkImage mark={mark} />
        <span className="truncate font-(family-name:--font-heading) font-bold text-(color:--ink-solid)">{name || "Your product name"}</span>
      </div>
      <div className="flex flex-col gap-3 bg-(color:--surface-chat) p-4">
        <p className="text-sm text-(color:--text-secondary)">{loginCopy}</p>
        <span
          data-testid="preview-button"
          className="self-start rounded bg-(color:--brand-primary) px-4 py-2 text-sm font-medium text-(color:--brand-primary-text)"
        >
          Sign in
        </span>
        <span className="self-start rounded-full border border-(color:--brand-accent) px-3 py-1 text-xs font-medium text-(color:--brand-accent)">
          Accent
        </span>
        <p className="rounded-lg bg-(color:--user-bubble-bg) p-3 text-sm text-(color:--conversation-body-color)">
          A sample message in the conversation.
        </p>
        <p className="text-xs text-(color:--text-tertiary)">Secondary text on the surface.</p>
      </div>
    </div>
  );
}

export function BrandPreview({ palette, name, loginCopy, light, dark }: BrandPreviewProps) {
  return (
    <section aria-label="Preview" className="flex flex-col gap-3">
      <h2 className="font-title text-lg font-semibold">Preview</h2>
      {palette ? (
        <div className="flex flex-col gap-4 sm:flex-row">
          <Pane label="Light preview" tokens={palette.light} fonts={palette.fonts} mark={light} name={name} loginCopy={loginCopy} />
          <Pane label="Dark preview" tokens={palette.dark} fonts={palette.fonts} mark={dark} name={name} loginCopy={loginCopy} />
        </div>
      ) : (
        <p data-testid="preview-unavailable" role="note" className="rounded border border-carbon/40 bg-white p-4 text-sm">
          The preview is unavailable until the colors and fonts are valid and form a readable theme.
        </p>
      )}
    </section>
  );
}
