import { useCallback, useEffect, useState } from "react";
import type { Organization } from "../api/account";
import type { CatalogApi, CatalogStatus } from "../api/catalog";
import { ApiError } from "../api/client";
import { NotFound } from "../components/NotFound";
import { Layers } from "lucide-react";
import {
  describeCatalogFailure,
  effectiveDefault,
  initialRows,
  publicationLabel,
  validateSelection,
  type Row,
} from "../catalog/model";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/Card";
import { Checkbox, Radio, RadioGroup } from "../ui/Choice";
import { EmptyState } from "../ui/EmptyState";
import { Input } from "../ui/Input";
import { PageHeader } from "../ui/PageHeader";
import { Skeleton, SkeletonText } from "../ui/Skeleton";

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

const CELL = "px-4 py-2 text-left align-middle";

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

  const defaultUpstream = discovery ? effectiveDefault(discovery.rows, discovery.preferredDefault) : "";
  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="Catalog" description="The models your members can choose, published under aliases." />
      {load.status === "loading" && (
        <div role="status" className="flex flex-col gap-4">
          <span className="sr-only">Loading catalog…</span>
          <Skeleton className="h-28" />
          <SkeletonText lines={3} />
        </div>
      )}
      {load.status === "error" && <Alert tone="destructive">{describeCatalogFailure(null, "load")}</Alert>}
      {load.status === "ready" && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <section aria-label="Catalog status" className="flex flex-col gap-2">
                <div>
                  <Badge tone={load.catalog.publication_state === "CURRENT" ? "success" : "warning"}>{publicationLabel(load.catalog.publication_state)}</Badge>
                </div>
                <p className="text-muted">Catalog revision {load.catalog.catalogue_revision}</p>
                {load.catalog.default_model && <p>Default model: {load.catalog.default_model}</p>}
              </section>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div className="flex flex-col gap-1">
                <CardTitle>Published aliases</CardTitle>
                <CardDescription>What members see in the client.</CardDescription>
              </div>
              <Button loading={busy} onClick={() => void refreshModels()}>
                Refresh models
              </Button>
            </CardHeader>
            <CardContent>
              {load.aliases.length > 0 ? (
                <ul aria-label="Published aliases" className="flex flex-wrap gap-2">
                  {load.aliases.map((alias) => (
                    <li key={alias} className="rounded-full border border-line bg-subtle px-3 py-1 text-body">
                      {alias}
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={Layers} title="No aliases are published." hint="Refresh the models from your gateway, choose what to publish and publish the catalog." />
              )}
            </CardContent>
          </Card>
        </>
      )}
      {notice && <Alert tone="success">{notice}</Alert>}
      {failure && <Alert tone="destructive">{failure}</Alert>}
      {problems.length > 0 && (
        <Alert tone="destructive">
          <ul className="list-disc pl-5">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </Alert>
      )}
      {discovery && (
        <Card>
          <CardHeader>
            <CardTitle>Model mapping</CardTitle>
            <CardDescription>Choose the models to publish, name each alias and pick the default.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <RadioGroup aria-label="Default model" value={defaultUpstream} onValueChange={(upstream) => setDiscovery({ ...discovery, preferredDefault: upstream })}>
              <div className="relative overflow-auto rounded-card border border-line">
                <table className="w-full border-collapse text-body">
                  <caption className="sr-only">Model mapping</caption>
                  <thead>
                    <tr>
                      {["Publish", "Upstream model", "Alias", "Default"].map((heading) => (
                        <th key={heading} scope="col" className={`${CELL} h-11 whitespace-nowrap border-b border-line bg-subtle font-semibold`}>
                          {heading}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {discovery.rows.map((row) => (
                      <tr key={row.upstream} className="border-t border-line first:border-t-0">
                        <td className={CELL}>
                          <Checkbox checked={row.selected} onCheckedChange={(checked) => edit(row.upstream, { selected: checked === true })} label={<span className="sr-only">Publish {row.upstream}</span>} />
                        </td>
                        <td className={`${CELL} font-mono`}>{row.upstream}</td>
                        <td className={CELL}>
                          <Input aria-label={`Alias for ${row.upstream}`} value={row.alias} disabled={!row.selected} onChange={(event) => edit(row.upstream, { alias: event.target.value })} className="min-w-40" />
                        </td>
                        <td className={CELL}>
                          <Radio value={row.upstream} disabled={!row.selected} label={<span className="sr-only">Default: {row.upstream}</span>} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </RadioGroup>
            <div>
              <Button loading={busy} onClick={() => void publish()}>
                Publish catalog
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  );
}