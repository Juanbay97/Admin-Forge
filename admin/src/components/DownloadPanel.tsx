import { Download as DownloadIcon, ExternalLink, FileJson, ShieldCheck, TriangleAlert } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
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
  const manifest = useQuery({ queryKey: ["portal", "manifest"], queryFn: () => services.downloads.latest(), retry: false });
  const offer = manifest.isSuccess ? pickInstaller(manifest.data, navigator.userAgent) : null;
  const configuration = useMutation({ mutationFn: async () => saveTextFile(configFile(await services.installer.config(organization.id))) });
  const download = useMutation({ mutationFn: async () => saveBlobFile(await services.installer.stamped(organization.id, code)) });

  return (
    <div className="flex flex-col gap-6">
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Your company code</CardTitle>
          <CardDescription>Forge reads it from the name of the installer you download here. If it ever asks, this is the code to enter.</CardDescription>
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
                  <div className="flex flex-col gap-3">
                    <Button size="lg" className="h-auto min-h-14 w-full max-w-md whitespace-normal py-3 text-section" aria-busy={download.isPending} disabled={download.isPending} onClick={() => download.mutate()}>
                      <DownloadIcon aria-hidden="true" className="size-6" />
                      Download Prometheon Forge
                    </Button>
                    <div className="flex flex-wrap items-center gap-3">
                      <Badge tone="neutral">v{manifest.data.version} {"\u00b7"} {formatBytes(offer.installer.size_bytes)}</Badge>
                      <span className="text-caption text-muted">Released {formatDate(manifest.data.released_at)}</span>
                      {download.isPending && <span role="status" className="text-caption text-muted">Preparing your download...</span>}
                    </div>
                    {download.isError && <Alert tone="destructive">The download could not be prepared. Try again in a moment.</Alert>}
                    <p className="text-caption text-muted">The file is named for your company (<code className="break-all font-mono">Prometheon-Forge-Setup-{code ?? "your-company"}.exe</code>): keep that name and Forge knows which company you belong to.</p>
                  </div>
                  <div className="rounded-control border border-line bg-subtle p-3 text-body">
                    <p className="flex min-h-10 items-center gap-2 font-medium text-fg"><ShieldCheck aria-hidden="true" className="size-4" />SHA-256 of the installer</p>
                    <div className="my-2 flex flex-wrap items-center gap-2">
                      <code data-testid="sha256" className="break-all select-all font-mono text-caption text-fg">{offer.installer.sha256}</code>
                      <CopyButton value={offer.installer.sha256} label="Copy hash" />
                    </div>
                    <p className="text-muted">The same for every company. In PowerShell: <code className="break-all font-mono">Get-FileHash .\Prometheon-Forge-Setup-{code ?? "your-company"}.exe -Algorithm SHA256</code></p>
                  </div>
                  <details className="rounded-control border border-line p-3 text-body">
                    <summary className="flex min-h-10 cursor-pointer items-center gap-2 font-medium text-fg">Advanced</summary>
                    <div className="mt-3 flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <Button variant="outline" className="h-auto min-h-10 whitespace-normal py-2 text-left" disabled={configuration.isPending} onClick={() => configuration.mutate()}>
                          <FileJson aria-hidden="true" className="size-4" />
                          Download configuration (forge-install.json)
                        </Button>
                        <span className="text-caption text-muted">Optional, for managed installs: it carries your company code, this server and the public keys the app trusts. It holds no password or key.</span>
                      </div>
                      {configuration.isError && <Alert tone="destructive">The configuration could not be prepared. Try again in a moment.</Alert>}
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
              <CardTitle><span className="mr-2 text-muted">2</span>Install</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="flex items-start gap-2 text-body text-muted">
                <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <span>Run the file you downloaded. The installer is not code-signed yet, so Windows SmartScreen may warn you: choose <strong className="text-fg">More info</strong>, then <strong className="text-fg">Run anyway</strong>.</span>
              </p>
            </CardContent>
          </Card>
        </li>
        <li>
          <Card>
            <CardHeader>
              <CardTitle><span className="mr-2 text-muted">3</span>Open Forge and sign in</CardTitle>
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
    </div>
  );
}
