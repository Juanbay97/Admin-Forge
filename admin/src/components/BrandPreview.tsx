import { useEffect, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
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
  /** The isotipo the client uses as its favicon; null shows the bundled Prometheon icon. */
  favicon: Mark | null;
}

/** Bundled favicon of the default look (the client falls back to its own default icon the same way). */
const DEFAULT_FAVICON = "/admin/brand/isotipo_claro.png";

// A decoded bitmap is drawn on a canvas: the admin CSP (`img-src 'self'`) forbids blob: and data: URLs.
function LogoCanvas({ bitmap, label, size }: { bitmap: ImageBitmap; label: string; size: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0);
  }, [bitmap]);
  return <canvas ref={ref} role="img" aria-label={label} className={`${size} w-auto`} />;
}

function MarkImage({ mark, label, size = "h-8" }: { mark: Mark | null; label?: string; size?: string }) {
  const { t } = useTranslation();
  if (mark?.bitmap) return <LogoCanvas bitmap={mark.bitmap} label={label ?? t("branding.preview.logoAlt")} size={size} />;
  if (mark?.url) return <img src={mark.url} alt="" className={`${size} w-auto`} />;
  return null;
}

// What the browser tab shows for the company: the page title is the company name and the icon is the isotipo.
function TabPreview({ name, favicon }: { name: string; favicon: Mark | null }) {
  const { t } = useTranslation();
  return (
    <div role="group" aria-label={t("branding.preview.tabGroup")} className="flex flex-col gap-1">
      <span className="text-sm font-medium">{t("branding.preview.tab")}</span>
      <div className="flex w-56 max-w-full items-center gap-2 rounded-t-lg border border-b-0 border-carbon/30 bg-white px-3 py-2 text-sm">
        <MarkImage mark={favicon ?? { url: DEFAULT_FAVICON }} label={t("branding.preview.faviconAlt")} size="h-4" />
        <span className="truncate">{name || t("branding.preview.displayName")}</span>
      </div>
    </div>
  );
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
  const { t } = useTranslation();
  const shownName = name || t("branding.preview.displayName");
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
        <span className="truncate font-(family-name:--font-heading) font-bold text-(color:--ink-solid)">{shownName}</span>
      </div>
      <div className="flex flex-col gap-3 bg-(color:--surface-chat) p-4">
        <h3 className="truncate font-(family-name:--font-heading) text-lg font-bold text-(color:--text-primary)">
          {t("branding.preview.welcome", { name: shownName })}
        </h3>
        <p className="text-sm text-(color:--text-secondary)">{loginCopy}</p>
        {[t("branding.preview.email"), t("branding.preview.password")].map((label) => (
          <span key={label} className="flex flex-col gap-1 text-xs text-(color:--text-secondary)">
            {label}
            <span className="h-8 rounded border border-(color:--border-heavy) bg-(color:--surface-primary)" />
          </span>
        ))}
        <span
          data-testid="preview-button"
          className="self-start rounded bg-(color:--brand-primary) px-4 py-2 text-sm font-medium text-(color:--brand-primary-text)"
        >
          {t("branding.preview.signIn")}
        </span>
        <span className="self-start rounded-full border border-(color:--brand-accent) px-3 py-1 text-xs font-medium text-(color:--brand-accent)">
          {t("branding.preview.accent")}
        </span>
        <p className="rounded-lg bg-(color:--user-bubble-bg) p-3 text-sm text-(color:--conversation-body-color)">
          {t("branding.preview.sampleMessage")}
        </p>
        <p className="text-xs text-(color:--text-tertiary)">{t("branding.preview.secondary")}</p>
      </div>
    </div>
  );
}

export function BrandPreview({ palette, name, loginCopy, light, dark, favicon }: BrandPreviewProps) {
  const { t } = useTranslation();
  return (
    <section aria-label={t("branding.preview.title")} className="flex flex-col gap-3">
      <h2 className="font-title text-lg font-semibold">{t("branding.preview.title")}</h2>
      <p className="text-sm">{t("branding.preview.intro")}</p>
      <TabPreview name={name} favicon={favicon} />
      {palette ? (
        <div className="flex flex-col gap-4 sm:flex-row">
          <Pane label={t("branding.preview.light")} tokens={palette.light} fonts={palette.fonts} mark={light} name={name} loginCopy={loginCopy} />
          <Pane label={t("branding.preview.dark")} tokens={palette.dark} fonts={palette.fonts} mark={dark} name={name} loginCopy={loginCopy} />
        </div>
      ) : (
        <p data-testid="preview-unavailable" role="note" className="rounded border border-carbon/40 bg-white p-4 text-sm">
          {t("branding.preview.unavailable")}
        </p>
      )}
    </section>
  );
}
