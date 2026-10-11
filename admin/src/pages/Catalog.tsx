import { useCallback, useEffect, useState } from "react";
import type { Organization } from "../api/account";
import type { CatalogApi, CatalogStatus } from "../api/catalog";
import { ApiError } from "../api/client";
import { NotFound } from "../components/NotFound";
import {
  describeCatalogFailure,
  effectiveDefault,
  initialRows,
  publicationLabel,
  validateSelection,
  type Row,
} from "../catalog/model";

interface CatalogProps {
  catalogApi: CatalogApi;
  organization: Organization;
  newOperationId?: () => string;
}

type Load =
  | { status: "loading" | "not-found" | "error" }
  | { status: "ready"; catalog: CatalogStatus; aliases: string[] };

interface Discovery {
  gatewayRevision: number;
  rows: Row[];
  preferredDefault: string;
}

const CELL = "px-3 py-2 text-left align-middle";
const BUTTON =
  "rounded bg-teal px-4 py-2 font-medium text-white transition-colors hover:bg-primary disabled:opacity-60";

async function fetchCatalog(catalogApi: CatalogApi, orgId: string): Promise<Load> {
  const catalog = await catalogApi.status(orgId);
  // A member can only read a catalogue that exists; an unpublished one has no aliases yet.
  const aliases = catalog.publication_state === "UNPUBLISHED" ? [] : (await catalogApi.published(orgId)).aliases;
  return { status: "ready", catalog, aliases };
}

export function Catalog({ catalogApi, organization, newOperationId = () => crypto.randomUUID() }: CatalogProps) {
  const orgId = organization.id;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(
    () =>
      fetchCatalog(catalogApi, orgId).catch((error: unknown): Load => ({
        status: error instanceof ApiError && error.status === 404 ? "not-found" : "error",
      })),
    [catalogApi, orgId],
  );

  useEffect(() => {
    let current = true;
    void reload().then((loaded) => current && setLoad(loaded));
    return () => {
      current = false;
    };
  }, [reload]);

  if (load.status === "not-found") return <NotFound />;

  async function refreshModels() {
    setBusy(true);
    setFailure(null);
    setProblems([]);
    setNotice(null);
    try {
      const found = await catalogApi.refresh(orgId);
      const rows = initialRows(found.model_ids);
      setDiscovery({ gatewayRevision: found.gateway_revision, rows, preferredDefault: rows[0]?.upstream ?? "" });
    } catch (error) {
      setDiscovery(null);
      setFailure(describeCatalogFailure(error, "refresh"));
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!discovery || load.status !== "ready") return;
    const selection = validateSelection(discovery.rows, effectiveDefault(discovery.rows, discovery.preferredDefault));
    setProblems(selection.ok ? [] : selection.problems);
    setFailure(null);
    setNotice(null);
    if (!selection.ok) return;
    setBusy(true);
    try {
      await catalogApi.publish(orgId, {
        aliases: selection.aliases,
        defaultAlias: selection.defaultAlias,
        expectedCatalogueRevision: load.catalog.catalogue_revision,
        expectedGatewayRevision: discovery.gatewayRevision,
        operationId: newOperationId(),
      });
      const count = Object.keys(selection.aliases).length;
      setNotice(`Published ${count} ${count === 1 ? "alias" : "aliases"}.`);
      setLoad(await reload());
    } catch (error) {
      setFailure(describeCatalogFailure(error, "publish"));
    } finally {
      setBusy(false);
    }
  }

  const edit = (upstream: string, change: Partial<Row>) =>
    setDiscovery((state) =>
      state && { ...state, rows: state.rows.map((row) => (row.upstream === upstream ? { ...row, ...change } : row)) },
    );

  return (
    <section className="flex flex-col gap-4">
      <h1 className="font-title text-2xl font-bold text-primary">Catalog</h1>
      {load.status === "loading" && <p role="status">Loading catalog…</p>}
      {load.status === "error" && (
        <p role="alert" className="font-medium text-red-800">
          {describeCatalogFailure(null, "load")}
        </p>
      )}
      {load.status === "ready" && (
        <>
          <p>
            Status: <strong>{publicationLabel(load.catalog.publication_state)}</strong>
          </p>
          <p>Catalog revision {load.catalog.catalogue_revision}</p>
          {load.catalog.default_model && <p>Default model: {load.catalog.default_model}</p>}
          <h2 className="font-title text-lg font-semibold">Published aliases</h2>
          {load.aliases.length > 0 ? (
            <ul aria-label="Published aliases" className="list-disc pl-6">
              {load.aliases.map((alias) => (
                <li key={alias}>{alias}</li>
              ))}
            </ul>
          ) : (
            <p>No aliases are published.</p>
          )}
          <div>
            <button type="button" disabled={busy} onClick={() => void refreshModels()} className={BUTTON}>
              Refresh models
            </button>
          </div>
        </>
      )}
      {notice && <p role="status">{notice}</p>}
      {failure && (
        <p role="alert" className="font-medium text-red-800">
          {failure}
        </p>
      )}
      {problems.length > 0 && (
        <div role="alert" className="font-medium text-red-800">
          <ul className="list-disc pl-6">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </div>
      )}
      {discovery && (
        <>
          <table className="w-full border-collapse overflow-hidden rounded-lg bg-white text-sm shadow">
            <caption className="sr-only">Model mapping</caption>
            <thead className="bg-primary text-sand">
              <tr>
                {["Publish", "Upstream model", "Alias", "Default"].map((heading) => (
                  <th key={heading} scope="col" className={CELL}>
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {discovery.rows.map((row) => (
                <tr key={row.upstream} className="border-t border-carbon/15">
                  <td className={CELL}>
                    <input
                      type="checkbox"
                      aria-label={`Publish ${row.upstream}`}
                      checked={row.selected}
                      onChange={(event) => edit(row.upstream, { selected: event.target.checked })}
                    />
                  </td>
                  <td className={CELL}>{row.upstream}</td>
                  <td className={CELL}>
                    <input
                      aria-label={`Alias for ${row.upstream}`}
                      value={row.alias}
                      disabled={!row.selected}
                      onChange={(event) => edit(row.upstream, { alias: event.target.value })}
                      className="rounded border border-carbon/40 px-2 py-1"
                    />
                  </td>
                  <td className={CELL}>
                    <input
                      type="radio"
                      name="default-model"
                      aria-label={`Default: ${row.upstream}`}
                      disabled={!row.selected}
                      checked={effectiveDefault(discovery.rows, discovery.preferredDefault) === row.upstream}
                      onChange={() => setDiscovery({ ...discovery, preferredDefault: row.upstream })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div>
            <button type="button" disabled={busy} onClick={() => void publish()} className={BUTTON}>
              Publish catalog
            </button>
          </div>
        </>
      )}
    </section>
  );
}