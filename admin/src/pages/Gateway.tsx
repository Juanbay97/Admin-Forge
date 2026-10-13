import { useEffect, useState } from "react";
import type { Organization } from "../api/account";
import { ApiError } from "../api/client";
import type { Gateway as GatewayState, GatewayApi } from "../api/gateway";
import { NotFound } from "../components/NotFound";
import { describeGatewayFailure, gatewayStateLabel } from "../gateway/model";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { Card, CardDescription, CardHeader, CardTitle } from "../ui/Card";
import { PageHeader } from "../ui/PageHeader";
import { Skeleton, SkeletonText } from "../ui/Skeleton";
import { Stat } from "../ui/Stat";

interface GatewayProps {
  gatewayApi: GatewayApi;
  organization: Organization;
}

type Load = { status: "loading" | "not-found" | "error" } | { status: "ready"; gateway: GatewayState };

/** Read-only: the gateway key belongs to the platform; an administrator sees only whether it is usable. */
export function Gateway({ gatewayApi, organization }: GatewayProps) {
  const orgId = organization.id;
  const [load, setLoad] = useState<Load>({ status: "loading" });

  useEffect(() => {
    let current = true;
    gatewayApi.get(orgId).then(
      (gateway) => current && setLoad({ status: "ready", gateway }),
      (error: unknown) => current && setLoad({ status: error instanceof ApiError && error.status === 404 ? "not-found" : "error" }),
    );
    return () => {
      current = false;
    };
  }, [gatewayApi, orgId]);

  if (load.status === "not-found") return <NotFound />;

  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Gateway" description="Where Forge sends model requests for your company." />
      {load.status === "loading" && (
        <div role="status" className="flex flex-col gap-4">
          <span className="sr-only">Loading gateway…</span>
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
          <SkeletonText lines={2} />
        </div>
      )}
      {load.status === "error" && <Alert tone="destructive">{describeGatewayFailure(null)}</Alert>}
      {load.status === "ready" && (
        <>
          <section aria-label="Gateway status">
            <dl className="grid gap-4 sm:grid-cols-2">
              <Stat label="Status">
                <Badge tone={load.gateway.status === "NOT_CONFIGURED" ? "warning" : "success"}>{gatewayStateLabel(load.gateway.status)}</Badge>
              </Stat>
              <Stat label="Usable platform keys">{load.gateway.revision}</Stat>
            </dl>
          </section>
          <Card className="max-w-2xl">
            <CardHeader>
              <CardTitle>Managed by the platform</CardTitle>
              <CardDescription>The gateway key is managed by the platform. Contact the platform operator to change it.</CardDescription>
            </CardHeader>
          </Card>
        </>
      )}
    </section>
  );
}