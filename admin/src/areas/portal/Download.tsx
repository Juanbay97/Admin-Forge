import { Download as DownloadIcon, ExternalLink, ShieldCheck, TriangleAlert } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { formatDate } from "../../lib/format";
import { deepLink, formatBytes, pickInstaller } from "../../portal/download";
import { Alert } from "../../ui/Alert";
import { Badge } from "../../ui/Badge";
import { Button, buttonVariants } from "../../ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../ui/Card";
import { CopyButton } from "../../ui/CopyButton";
import { PageHeader } from "../../ui/PageHeader";
import { Skeleton } from "../../ui/Skeleton";
import { usePortal } from "./PortalLayout";

export function Download() {
  const { services, code, organization } = usePortal();
  const manifest = useQuery({ queryKey: ["portal", "manifest"], queryFn: () => services.downloads.latest(), retry: false });
  const offer = manifest.isSuccess ? pickInstaller(manifest.data, navigator.userAgent) : null;

  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Get the app" description={`Install Forge on your computer and connect it to ${organization.display_name}.`} />

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Your company code</CardTitle>
          <CardDescription>Forge asks for this the first time you open it, so it shows your company&apos;s branding.</CardDescription>
        </CardHeader>
        <CardContent>
          {code ? (
            <div className="flex flex-wrap items-center gap-3">
              <code data-testid="company-code" className="select-all rounded-control bg-subtle px-4 py-2 font-mono text-section font-semibold text-fg">{code}</code>
              <CopyButton value={code} label="Copy code" />
            </div>
          ) : (
            <Alert tone="warning">Your company code is not available here. Ask your company administrator for it.</Alert>
          )}
        </CardContent>
      </Card>

      <ol className="grid max-w-3xl gap-4">
        <li>
          <Card>
            <CardHeader>
              <CardTitle><span className="mr-2 text-muted">1</span>Download</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {manifest.isPending && <div role="status" aria-label="Checking for the installer"><Skeleton className="h-10 w-56" /></div>}
              {manifest.isError && (
                <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void manifest.refetch()}>Try again</Button>}>
                  The installer information could not be loaded.
                </Alert>
              )}
              {offer?.kind === "none" && <Alert tone="info" title="The installer is not available yet">Your company administrator will let you know when it is published. Your company code above is already yours.</Alert>}
              {offer?.kind === "unsupported" && <Alert tone="warning" title="Windows only for now">The Forge desktop app is available for Windows. You are on {offer.system}; open this page on a Windows computer to download it.</Alert>}
              {offer?.kind === "download" && manifest.data && (
                <>
                  <div className="flex flex-wrap items-center gap-3">
                    <a href={offer.installer.url} download className={buttonVariants({ size: "lg" })}>
                      <DownloadIcon aria-hidden="true" className="size-5" />
                      Download for Windows
                    </a>
                    <Badge tone="neutral">v{manifest.data.version} · {formatBytes(offer.installer.size_bytes)}</Badge>
                    <span className="text-caption text-muted">Released {formatDate(manifest.data.released_at)}</span>
                  </div>
                  <details className="rounded-control border border-line bg-subtle p-3 text-body">
                    <summary className="flex min-h-10 cursor-pointer items-center gap-2 font-medium text-fg"><ShieldCheck aria-hidden="true" className="size-4" />Verify the download</summary>
                    <p className="mt-2 text-muted">The file&apos;s SHA-256 should be exactly:</p>
                    <div className="my-2 flex flex-wrap items-center gap-2">
                      <code data-testid="sha256" className="break-all select-all font-mono text-caption text-fg">{offer.installer.sha256}</code>
                      <CopyButton value={offer.installer.sha256} label="Copy hash" />
                    </div>
                    <p className="text-muted">In PowerShell: <code className="font-mono">Get-FileHash .\Forge-Setup.exe -Algorithm SHA256</code></p>
                  </details>
                </>
              )}
            </CardContent>
          </Card>
        </li>
        <li>
          <Card>
            <CardHeader>
              <CardTitle><span className="mr-2 text-muted">2</span>Install</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="flex items-start gap-2 text-body text-muted">
                <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <span>The installer is not code-signed yet, so Windows SmartScreen may warn you. Choose <strong className="text-fg">More info</strong>, then <strong className="text-fg">Run anyway</strong>.</span>
              </p>
            </CardContent>
          </Card>
        </li>
        <li>
          <Card>
            <CardHeader>
              <CardTitle><span className="mr-2 text-muted">3</span>Open Forge and enter your company code</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {code && (
                <div>
                  <a href={deepLink(window.location.origin, code)} className={buttonVariants({ variant: "outline" })}>
                    <ExternalLink aria-hidden="true" className="size-4" />
                    Open Forge
                  </a>
                </div>
              )}
              <p className="text-body text-muted">{code ? <>Not opening? Enter code <strong className="text-fg">{code}</strong> manually in the app.</> : "Enter your company code in the app when it asks for it."}</p>
            </CardContent>
          </Card>
        </li>
      </ol>
    </section>
  );
}