import { Download, FileCheck2, KeyRound, LineChart, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import type { DownloadsApi, InstallerManifest } from "../api/downloads";
import { defaultTheme } from "../brand/theme";
import { LanguageSwitch } from "../i18n/LanguageSwitch";
import { formatDate } from "../lib/format";
import { formatBytes } from "../portal/download";
import { Alert } from "../ui/Alert";
import { Button, buttonVariants } from "../ui/Button";
import { cn } from "../lib/cn";

const SIGN_IN = "/admin/";
const LICENSE = "https://www.apache.org/licenses/LICENSE-2.0";
const ON_DARK = "border border-on-nav-muted bg-transparent text-on-nav hover:bg-nav-hover";

const FEATURES = [
  { icon: KeyRound, id: "models" },
  { icon: Users, id: "teams" },
  { icon: LineChart, id: "usage" },
] as const;

type Manifest = { state: "loading" } | { state: "error" } | { state: "ready"; manifest: InstallerManifest | null };

/** The public face of the domain: what the product is, a way in and the Windows installer when one is published. */
export function Landing({ downloads }: { downloads: DownloadsApi }) {
  const { t } = useTranslation(["landing", "common"]);
  const [load, setLoad] = useState<Manifest>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    setLoad({ state: "loading" });
    downloads.latest().then(
      (manifest) => current && setLoad({ state: "ready", manifest }),
      () => current && setLoad({ state: "error" }),
    );
    return () => {
      current = false;
    };
  }, [downloads, attempt]);

  const windows = load.state === "ready" ? load.manifest?.platforms.windows : undefined;

  return (
    <div className="flex min-h-screen flex-col bg-app text-fg">
      <header className="bg-nav text-on-nav">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <img src={defaultTheme.assets.markOnDark} alt="" className="h-9 w-auto" />
            <span className="truncate font-title text-section font-semibold">{defaultTheme.name}</span>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <LanguageSwitch />
            <a href={SIGN_IN} className={cn(buttonVariants({ variant: "outline" }), ON_DARK)}>{t("signIn")}</a>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <section aria-labelledby="hero-heading" className="bg-nav text-on-nav">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 pb-16 pt-10 sm:px-6 sm:pb-24 sm:pt-16">
            <h1 id="hero-heading" className="max-w-3xl font-title text-4xl font-bold leading-tight sm:text-5xl">
              {t("hero.title")}
            </h1>
            <p className="max-w-2xl text-section text-on-nav">{t("hero.text")}</p>
            <div className="flex flex-wrap gap-3">
              <a href={SIGN_IN} className={cn(buttonVariants({ size: "lg" }), "bg-surface text-fg hover:bg-sand")}>{t("signIn")}</a>
              <a href="#download" className={cn(buttonVariants({ size: "lg", variant: "outline" }), ON_DARK)}>{t("hero.getApp")}</a>
            </div>
          </div>
        </section>

        <div className="mx-auto flex w-full max-w-6xl flex-col gap-12 px-4 py-12 sm:px-6">
        <section aria-label={t("features.label")} className="grid gap-4 md:grid-cols-3">
          {FEATURES.map(({ icon: Icon, id }) => (
            <article key={id} className="flex flex-col gap-2 rounded-card border border-line bg-surface p-5 shadow-card">
              <Icon aria-hidden="true" className="size-6 text-action" />
              <h2 className="font-title text-card font-semibold">{t(`features.${id}.title`)}</h2>
              <p className="text-body text-muted">{t(`features.${id}.text`)}</p>
            </article>
          ))}
        </section>

        <section id="download" aria-labelledby="download-heading" className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 shadow-card sm:p-6">
          <div className="flex flex-col gap-1">
            <h2 id="download-heading" className="font-title text-section font-semibold">{t("download.title")}</h2>
            <p className="text-body text-muted">{t("download.text")}</p>
          </div>
          {load.state === "loading" && <p role="status" className="text-body text-muted">{t("download.checking")}</p>}
          {load.state === "error" && (
            <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => setAttempt((value) => value + 1)}>{t("common:actions.tryAgain")}</Button>}>
              {t("download.loadError")}
            </Alert>
          )}
          {load.state === "ready" && !windows && (
            <Alert tone="info" title={t("download.notPublishedTitle")}>{t("download.notPublishedBody")}</Alert>
          )}
          {load.state === "ready" && windows && load.manifest && (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <a href={windows.url} download className={buttonVariants({ size: "lg" })}>
                  <Download aria-hidden="true" className="size-5" />
                  {t("download.title")}
                </a>
                <span className="text-body text-fg">{t("download.version", { version: load.manifest.version })}</span>
                <span className="text-body text-muted">{formatBytes(windows.size_bytes)}</span>
                <span className="text-caption text-muted">{t("download.released", { date: formatDate(load.manifest.released_at) })}</span>
              </div>
              <div className="flex flex-col gap-1 rounded-control border border-line bg-subtle p-3">
                <p className="flex items-center gap-2 text-body font-medium"><FileCheck2 aria-hidden="true" className="size-4" />{t("download.sha")}</p>
                <code data-testid="sha256" className="break-all select-all font-mono text-caption">{windows.sha256}</code>
                <p className="text-caption text-muted">{t("download.shaHint")}</p>
              </div>
            </div>
          )}
        </section>
        </div>
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-6 text-caption text-muted sm:px-6">
          <p>
            <Trans t={t} i18nKey="footer" components={{ license: <a href={LICENSE} rel="noreferrer noopener" className="font-medium text-on-action-soft underline underline-offset-2 outline-focus focus-visible:outline-2" /> }} />
          </p>
        </div>
      </footer>
    </div>
  );
}
