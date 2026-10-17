import { Download as DownloadIcon, ExternalLink, FileJson, ShieldCheck, TriangleAlert } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Trans, useTranslation } from "react-i18next";
import type { Organization } from "../api/account";
import type { Services } from "../api/services";
import { formatDate } from "../lib/format";
import { configFile, deepLink, formatBytes, pickInstaller, saveBlobFile, saveTextFile } from "../portal/download";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { Button, buttonVariants } from "../ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/Card";
import { CopyButton } from "../ui/CopyButton";
import { Skeleton } from "../ui/Skeleton";

interface DownloadPanelProps {
  services: Services;
  organization: Organization;
  /** The company code members type in the desktop app (from the company branding read); null while unknown. */
  code: string | null;
}

/** The installer, its checksum, the company configuration file and the install steps: the same for every role that belongs to a company. */
export function DownloadPanel({ services, organization, code }: DownloadPanelProps) {
  const { t } = useTranslation();
  const manifest = useQuery({ queryKey: ["portal", "manifest"], queryFn: () => services.downloads.latest(), retry: false });
  const offer = manifest.isSuccess ? pickInstaller(manifest.data, navigator.userAgent) : null;
  const configuration = useMutation({ mutationFn: async () => saveTextFile(configFile(await services.installer.config(organization.id))) });
  const download = useMutation({ mutationFn: async () => saveBlobFile(await services.installer.stamped(organization.id, code)) });

  return (
    <div className="flex flex-col gap-6">
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>{t("download.panel.codeTitle")}</CardTitle>
          <CardDescription>{t("download.panel.codeDescription")}</CardDescription>
        </CardHeader>
        <CardContent>
          {code ? (
            <div className="flex flex-wrap items-center gap-3">
              <code data-testid="company-code" className="select-all rounded-control bg-subtle px-4 py-2 font-mono text-section font-semibold text-fg">{code}</code>
              <CopyButton value={code} label={t("download.panel.copyCode")} />
            </div>
          ) : (
            <Alert tone="warning">{t("download.panel.codeUnavailable")}</Alert>
          )}
        </CardContent>
      </Card>

      <ol className="grid max-w-3xl gap-4">
        <li>
          <Card>
            <CardHeader>
              <CardTitle><span className="mr-2 text-muted">1</span>{t("download.panel.stepDownload")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {manifest.isPending && <div role="status" aria-label={t("download.panel.checking")}><Skeleton className="h-10 w-56" /></div>}
              {manifest.isError && (
                <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void manifest.refetch()}>{t("actions.tryAgain")}</Button>}>
                  {t("download.panel.loadError")}
                </Alert>
              )}
              {offer?.kind === "none" && <Alert tone="info" title={t("download.panel.noneTitle")}>{t("download.panel.noneBody")}</Alert>}
              {offer?.kind === "unsupported" && <Alert tone="warning" title={t("download.panel.windowsOnlyTitle")}>{t("download.panel.windowsOnlyBody", { system: offer.system })}</Alert>}
              {offer?.kind === "download" && manifest.data && (
                <>
                  <div className="flex flex-col gap-3">
                    <Button size="lg" className="h-auto min-h-14 w-full max-w-md whitespace-normal py-3 text-section" aria-busy={download.isPending} disabled={download.isPending} onClick={() => download.mutate()}>
                      <DownloadIcon aria-hidden="true" className="size-6" />
                      {t("download.panel.button")}
                    </Button>
                    <div className="flex flex-wrap items-center gap-3">
                      <Badge tone="neutral">v{manifest.data.version} {"\u00b7"} {formatBytes(offer.installer.size_bytes)}</Badge>
                      <span className="text-caption text-muted">{t("download.panel.released", { date: formatDate(manifest.data.released_at) })}</span>
                      {download.isPending && <span role="status" className="text-caption text-muted">{t("download.panel.preparing")}</span>}
                    </div>
                    {download.isError && <Alert tone="destructive">{t("download.panel.downloadFailed")}</Alert>}
                    <p className="text-caption text-muted"><Trans t={t} i18nKey="download.panel.fileName" values={{ code: code ?? t("download.panel.fileNameFallback") }} components={{ code: <code className="break-all font-mono" /> }} /></p>
                  </div>
                  <div className="rounded-control border border-line bg-subtle p-3 text-body">
                    <p className="flex min-h-10 items-center gap-2 font-medium text-fg"><ShieldCheck aria-hidden="true" className="size-4" />{t("download.panel.sha")}</p>
                    <div className="my-2 flex flex-wrap items-center gap-2">
                      <code data-testid="sha256" className="break-all select-all font-mono text-caption text-fg">{offer.installer.sha256}</code>
                      <CopyButton value={offer.installer.sha256} label={t("download.panel.copyHash")} />
                    </div>
                    <p className="text-muted"><Trans t={t} i18nKey="download.panel.shaNote" values={{ code: code ?? t("download.panel.fileNameFallback") }} components={{ code: <code className="break-all font-mono" /> }} /></p>
                  </div>
                  <details className="rounded-control border border-line p-3 text-body">
                    <summary className="flex min-h-10 cursor-pointer items-center gap-2 font-medium text-fg">{t("download.panel.advanced")}</summary>
                    <div className="mt-3 flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <Button variant="outline" className="h-auto min-h-10 whitespace-normal py-2 text-left" disabled={configuration.isPending} onClick={() => configuration.mutate()}>
                          <FileJson aria-hidden="true" className="size-4" />
                          {t("download.panel.configButton")}
                        </Button>
                        <span className="text-caption text-muted">{t("download.panel.configNote")}</span>
                      </div>
                      {configuration.isError && <Alert tone="destructive">{t("download.panel.configFailed")}</Alert>}
                    </div>
                  </details>
                </>
              )}
            </CardContent>
          </Card>
        </li>
        <li>
          <Card>
            <CardHeader>
              <CardTitle><span className="mr-2 text-muted">2</span>{t("download.panel.stepInstall")}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="flex items-start gap-2 text-body text-muted">
                <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <span><Trans t={t} i18nKey="download.panel.installNote" components={{ strong: <strong className="text-fg" /> }} /></span>
              </p>
            </CardContent>
          </Card>
        </li>
        <li>
          <Card>
            <CardHeader>
              <CardTitle><span className="mr-2 text-muted">3</span>{t("download.panel.stepOpen")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {code && (
                <div>
                  <a href={deepLink(window.location.origin, code)} className={buttonVariants({ variant: "outline" })}>
                    <ExternalLink aria-hidden="true" className="size-4" />
                    {t("download.panel.openForge")}
                  </a>
                </div>
              )}
              <p className="text-body text-muted">{code ? <Trans t={t} i18nKey="download.panel.notOpening" values={{ code }} components={{ strong: <strong className="text-fg" /> }} /> : t("download.panel.enterCode")}</p>
            </CardContent>
          </Card>
        </li>
      </ol>
    </div>
  );
}
