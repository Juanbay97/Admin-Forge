import { useEffect, useState } from "react";
import type { Organization } from "../api/account";
import { ApiError } from "../api/client";
import type { Gateway as GatewayState, GatewayApi } from "../api/gateway";
import { NotFound } from "../components/NotFound";
import { describeGatewayFailure, gatewayStateLabel } from "../gateway/model";

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
    <section className="flex flex-col gap-4">
      <h1 className="font-title text-2xl font-bold text-primary">Gateway</h1>
      {load.status === "loading" && <p role="status">Loading gateway...</p>}
      {load.status === "error" && (
        <p role="alert" className="font-medium text-red-800">
          {describeGatewayFailure(null)}
        </p>
      )}
      {load.status === "ready" && (
        <>
          <p>
            Status: <strong>{gatewayStateLabel(load.gateway.status)}</strong>
          </p>
          <p>Usable platform keys: {load.gateway.revision}</p>
          <p className="max-w-lg text-sm">The gateway key is managed by the platform. Contact the platform operator to change it.</p>
        </>
      )}
    </section>
  );
}
