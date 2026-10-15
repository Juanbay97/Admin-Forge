import { LineChart } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { DownloadCard } from "../../components/DownloadCard";
import { formatTokens } from "../../lib/format";
import { windowFor } from "../../platform/range";
import { tokensOf } from "../../platform/usage";
import { buttonVariants } from "../../ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../ui/Card";
import { PageHeader } from "../../ui/PageHeader";
import { Skeleton } from "../../ui/Skeleton";
import { useIdentity } from "../../shell/IdentityBoundary";
import { usePortal } from "./PortalLayout";

export function Home() {
  const { services, organization, code } = usePortal();
  const identity = useIdentity();
  const window7 = windowFor(7);
  const usage = useQuery({ queryKey: ["portal", "usage", organization.id, window7], queryFn: () => services.usage.mine(organization.id, window7), retry: false });
  const first = identity.account.display_name.split(/\s+/)[0] ?? "there";

  return (
    <section className="flex flex-col gap-6">
      <PageHeader title={`Welcome, ${first}`} description={`You are part of ${organization.display_name}.`} />
      <div className="grid gap-4 md:grid-cols-2">
        <DownloadCard services={services} to="/portal/download" code={code} />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><LineChart aria-hidden="true" className="size-5 text-muted" />Your usage, last 7 days</CardTitle>
            <CardDescription>Only you can see this.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {usage.isPending ? (
              <Skeleton className="h-8 w-32" />
            ) : usage.data ? (
              <p className="font-title text-section font-semibold text-fg">{formatTokens(tokensOf(usage.data))} <span className="text-body font-normal text-muted">tokens in {usage.data.requests} {usage.data.requests === 1 ? "request" : "requests"}</span></p>
            ) : (
              <p className="text-body text-muted">{usage.isError ? "Your usage could not be loaded." : "Usage will appear here once the app is in use."}</p>
            )}
            <Link to="/portal/usage" className={buttonVariants({ variant: "outline" })}>See my usage</Link>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}