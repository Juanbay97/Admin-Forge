import { ArrowRight, Download as DownloadIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { Services } from "../api/services";
import { formatBytes } from "../portal/download";
import { buttonVariants } from "../ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";

interface DownloadCardProps {
  services: Services;
  /** The page of the area that holds the full download panel. */
  to: string;
  /** The company code, when the area knows it (members type it in the desktop app). */
  code?: string | null;
}

/** The dashboard entry of the download area: what is published right now and the way to the full page. */
export function DownloadCard({ services, to, code }: DownloadCardProps) {
  const { t } = useTranslation();
  const manifest = useQuery({ queryKey: ["portal", "manifest"], queryFn: () => services.downloads.latest(), retry: false });
  const windows = manifest.data?.platforms.windows;
  const heading = useId();
  return (
    <Card aria-labelledby={heading}>
      <CardHeader>
        <CardTitle id={heading} className="flex items-center gap-2"><DownloadIcon aria-hidden="true" className="size-5 text-muted" />{t("download.title")}</CardTitle>
        <CardDescription>{code ? <Trans t={t} i18nKey="download.card.descriptionWithCode" values={{ code }} components={{ strong: <strong className="text-fg" /> }} /> : t("download.card.description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {manifest.isPending ? (
          <Skeleton className="h-6 w-40" />
        ) : windows && manifest.data ? (
          <p className="text-body text-fg"><Trans t={t} i18nKey="download.card.windowsInstaller" values={{ version: manifest.data.version, size: formatBytes(windows.size_bytes) }} components={{ strong: <strong />, size: <span className="text-muted" /> }} /></p>
        ) : (
          <p className="text-body text-muted">{manifest.isError ? t("download.card.loadError") : t("download.card.notPublished")}</p>
        )}
        <div>
          <Link to={to} className={buttonVariants({})}>{t("download.card.action")}<ArrowRight aria-hidden="true" className="size-4" /></Link>
        </div>
      </CardContent>
    </Card>
  );
}
