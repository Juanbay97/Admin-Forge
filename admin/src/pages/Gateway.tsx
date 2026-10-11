import { useEffect, useState, type FormEvent } from "react";
import type { Organization } from "../api/account";
import { ApiError } from "../api/client";
import type { Gateway as GatewayState, GatewayApi } from "../api/gateway";
import { NotFound } from "../components/NotFound";
import { chooseEndpoint, describeGatewayFailure, gatewayStateLabel } from "../gateway/model";

interface GatewayProps {
  gatewayApi: GatewayApi;
  organization: Organization;
}

type Load = { status: "loading" | "not-found" | "error" } | { status: "ready"; gateway: GatewayState };

const FIELD = "rounded border border-carbon/40 px-3 py-2 text-base";

export function Gateway({ gatewayApi, organization }: GatewayProps) {
  const orgId = organization.id;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [endpoint, setEndpoint] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    gatewayApi.get(orgId).then(
      (gateway) => {
        if (!current) return;
        setLoad({ status: "ready", gateway });
        setEndpoint(chooseEndpoint(gateway));
      },
      (error: unknown) => current && setLoad({ status: error instanceof ApiError && error.status === 404 ? "not-found" : "error" }),
    );
    return () => {
      current = false;
    };
  }, [gatewayApi, orgId, attempt]);

  if (load.status === "not-found") return <NotFound />;

  function reload() {
    setLoad({ status: "loading" });
    setFailure(null);
    setConflict(false);
    setAttempt((count) => count + 1);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (load.status !== "ready") return;
    const { revision } = load.gateway;
    const key = apiKey;
    setApiKey(""); // write-only: the secret leaves the page the moment it is submitted
    setBusy(true);
    setFailure(null);
    setConflict(false);
    try {
      const saved = await gatewayApi.save(orgId, { endpoint, apiKey: key, expectedRevision: revision });
      setLoad((state) => (state.status === "ready" ? { status: "ready", gateway: { ...state.gateway, ...saved } } : state));
    } catch (error) {
      setFailure(describeGatewayFailure(error, "save"));
      setConflict(error instanceof ApiError && error.code === "REVISION_CONFLICT");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h1 className="font-title text-2xl font-bold text-primary">Gateway</h1>
      {load.status === "loading" && <p role="status">Loading gateway…</p>}
      {load.status === "error" && (
        <p role="alert" className="font-medium text-red-800">
          {describeGatewayFailure(null, "load")}
        </p>
      )}
      {load.status === "ready" && (
        <>
          <p>
            Status: <strong>{gatewayStateLabel(load.gateway.status)}</strong>
          </p>
          <p>Revision {load.gateway.revision}</p>
          <form onSubmit={save} className="flex max-w-lg flex-col gap-4 rounded-lg bg-white p-6 shadow">
            <label className="flex flex-col gap-1 text-sm font-medium">
              Gateway base URL
              <select value={endpoint} onChange={(event) => setEndpoint(event.target.value)} className={FIELD}>
                {load.gateway.allowed_endpoints.map((allowed) => (
                  <option key={allowed} value={allowed}>
                    {allowed}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              API key
              <input
                type="password"
                autoComplete="off"
                required
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                className={FIELD}
              />
            </label>
            <p className="text-sm">The key is write-only. It is never shown again once saved.</p>
            {failure && (
              <p role="alert" className="text-sm font-medium text-red-800">
                {failure}
              </p>
            )}
            <div className="flex gap-3">
              <button
                type="submit"
                disabled={busy}
                className="rounded bg-teal px-4 py-2 font-medium text-white transition-colors hover:bg-primary disabled:opacity-60"
              >
                Save key
              </button>
              {conflict && (
                <button
                  type="button"
                  onClick={reload}
                  className="rounded border border-teal px-4 py-2 text-teal transition-colors hover:bg-teal hover:text-white"
                >
                  Reload
                </button>
              )}
            </div>
          </form>
        </>
      )}
    </section>
  );
}