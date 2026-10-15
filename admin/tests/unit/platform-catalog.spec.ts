import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createPlatformApi } from "../../src/api/platform";
import { buildRows, describeCatalogFailure, filterRows, mergeDiscovery, preferredDefault, KEY_STATES } from "../../src/catalog/platformModel";
import { effectiveDefault, validateSelection } from "../../src/catalog/model";

const fixture = (name: string): unknown => JSON.parse(readFileSync(new URL(`../fixtures/platform/${name}.json`, import.meta.url), "utf8"));
const P = "/forge/v1/platform";
const ORG = "11111111-1111-4111-8111-111111111111";

interface Call { method: string; path: string; body?: unknown }
function api(replies: Record<string, unknown>) {
  const calls: Call[] = [];
  const client: ApiClient = {
    async request(method, path, body) {
      calls.push({ method, path, body });
      const reply = replies[`${method} ${path}`];
      if (reply === undefined) throw new ApiError(404, "NOT_FOUND", "x");
      return reply as never;
    },
  };
  return { platform: createPlatformApi(client), calls };
}

test.describe("platform catalog api (fixtures are the real response shapes)", () => {
  test("reads an unconfigured and a configured company", async () => {
    const { platform } = api({ [`GET ${P}/companies/${ORG}/catalog`]: fixture("catalog-unconfigured") });
    expect(await platform.catalog(ORG)).toEqual({ configured: false });
    const { platform: second } = api({ [`GET ${P}/companies/${ORG}/catalog`]: fixture("catalog-unpublished") });
    const read = await second.catalog(ORG);
    expect(read.configured && read.catalogue.state).toBe("UNPUBLISHED");
  });

  test("discover posts an empty body and parses every per-key state", async () => {
    const { platform, calls } = api({ [`POST ${P}/companies/${ORG}/catalog/discover`]: fixture("catalog-discovery") });
    const found = await platform.discoverModels(ORG);
    expect(calls[0]).toEqual({ method: "POST", path: `${P}/companies/${ORG}/catalog/discover`, body: {} });
    expect(found.keys.map((key) => key.state)).toEqual(["ok", "unreachable"]);
    expect(found.model_ids).toHaveLength(4);
    expect(found.discovered_at).toBe("2026-10-14T12:00:00+00:00");
  });

  test("publish sends the exact body the route validates", async () => {
    const { platform, calls } = api({ [`PUT ${P}/companies/${ORG}/catalog`]: fixture("catalog-published") });
    const done = await platform.publishCatalog(ORG, { expectedCatalogueRevision: 0, expectedGatewayRevision: 1, aliases: { fast: "gpt-4o-mini" }, defaultAlias: "fast" });
    expect(calls[0]?.body).toEqual({ expected_catalogue_revision: 0, expected_gateway_revision: 1, aliases: { fast: "gpt-4o-mini" }, default_alias: "fast" });
    expect(done).toEqual({ revision: 1, default_model: "fast", models: ["fast", "smart"] });
  });

  test("an unexpected shape is refused at the boundary", async () => {
    const { platform } = api({ [`GET ${P}/companies/${ORG}/catalog`]: { configured: true, surprise: 1 } });
    await expect(platform.catalog(ORG)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    const { platform: second } = api({ [`POST ${P}/companies/${ORG}/catalog/discover`]: { keys: [{ key_id: ORG, label: "k", origin: "o", priority: 1, state: "exploded", model_count: 0, model_ids: [] }], model_ids: [], discovered_at: null } });
    await expect(second.discoverModels(ORG)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

test.describe("platform catalog model", () => {
  const ids = ["claude-3-5-sonnet", "combo/fast", "gpt-4o", "gpt-4o-mini"];

  test("rows start unselected with a legal alias suggested for every model", () => {
    const rows = buildRows(ids, {});
    expect(rows.map((row) => row.selected)).toEqual([false, false, false, false]);
    expect(rows.map((row) => row.alias)).toEqual(["claude-3-5-sonnet", "combo-fast", "gpt-4o", "gpt-4o-mini"]);
  });

  test("the published selection preselects its models under their published aliases, and the default comes from it", () => {
    const published = { fast: "gpt-4o-mini", smart: "claude-3-5-sonnet" };
    const rows = buildRows(ids, published);
    expect(rows.filter((row) => row.selected).map((row) => [row.upstream, row.alias])).toEqual([["claude-3-5-sonnet", "smart"], ["gpt-4o-mini", "fast"]]);
    expect(preferredDefault(published, "fast")).toBe("gpt-4o-mini");
    expect(preferredDefault(published, null)).toBe("");
    expect(preferredDefault({}, "fast")).toBe("");
  });

  test("a new discovery keeps the edits made so far and drops what is no longer served", () => {
    const edited = buildRows(ids, {}).map((row) => (row.upstream === "gpt-4o" ? { ...row, selected: true, alias: "main" } : row));
    const merged = mergeDiscovery(edited, ["gpt-4o", "gpt-5", "combo/fast"]);
    expect(merged.map((row) => row.upstream)).toEqual(["combo/fast", "gpt-4o", "gpt-5"]);
    expect(merged.find((row) => row.upstream === "gpt-4o")).toMatchObject({ selected: true, alias: "main" });
    expect(merged.find((row) => row.upstream === "gpt-5")).toMatchObject({ selected: false, alias: "gpt-5" });
  });

  test("search matches the model id or its alias, ignoring case and surrounding spaces", () => {
    const rows = buildRows(ids, {}).map((row) => (row.upstream === "gpt-4o" ? { ...row, alias: "Main-Model".toLowerCase() } : row));
    expect(filterRows(rows, "  GPT ").map((row) => row.upstream)).toEqual(["gpt-4o", "gpt-4o-mini"]);
    expect(filterRows(rows, "main").map((row) => row.upstream)).toEqual(["gpt-4o"]);
    expect(filterRows(rows, "")).toHaveLength(4);
    expect(filterRows(rows, "zzz")).toEqual([]);
  });

  test("the selection reuses the company rules: aliases are unique and legal, one default, at least one model", () => {
    const rows = buildRows(ids, {});
    expect(validateSelection(rows, "")).toEqual({ ok: false, problems: ["Select at least one model."] });
    const chosen = rows.map((row) => (row.upstream.startsWith("gpt") ? { ...row, selected: true, alias: "same" } : row));
    const result = validateSelection(chosen, effectiveDefault(chosen, ""));
    expect(result.ok).toBe(false);
    const fixed = chosen.map((row) => (row.upstream === "gpt-4o-mini" ? { ...row, alias: "mini" } : row));
    expect(validateSelection(fixed, effectiveDefault(fixed, "gpt-4o-mini"))).toEqual({ ok: true, aliases: { same: "gpt-4o", mini: "gpt-4o-mini" }, defaultAlias: "mini" });
  });

  test("every per-key state has a label and a tone; failures never echo the server", () => {
    expect(Object.keys(KEY_STATES).sort()).toEqual(["disabled", "inactive", "no_key", "ok", "unreachable", "unreadable"]);
    expect(describeCatalogFailure(new ApiError(409, "REVISION_CONFLICT", "secret detail"), "publish")).toMatch(/changed/);
    expect(describeCatalogFailure(new ApiError(409, "NO_ACTIVE_MEMBER", "x"), "publish")).toMatch(/no active member/);
    expect(describeCatalogFailure(new ApiError(422, "INVALID_REQUEST", "x"), "publish")).toMatch(/not accepted/);
    expect(describeCatalogFailure(new ApiError(422, "INVALID_REQUEST", "secret detail"), "publish")).not.toMatch(/secret/);
    expect(describeCatalogFailure(new ApiError(403, "MFA_REQUIRED", "x"), "discover")).toMatch(/verification/i);
    expect(describeCatalogFailure(new ApiError(503, "SERVICE_UNAVAILABLE", "x"), "discover")).toMatch(/could not be completed/);
    expect(describeCatalogFailure(null, "load")).toMatch(/could not be loaded/);
  });
});
