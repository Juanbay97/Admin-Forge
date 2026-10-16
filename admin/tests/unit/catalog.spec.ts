import { expect, test } from "@playwright/test";
import { createCatalogApi } from "../../src/api/catalog";
import { ApiError, type ApiClient } from "../../src/api/client";
import {
  describeCatalogFailure,
  effectiveDefault,
  initialRows,
  publicationLabel,
  suggestAlias,
  validateSelection,
  type Row,
} from "../../src/catalog/model";

function recorder(reply: unknown) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const client: ApiClient = {
    async request<T>(method: string, path: string, body?: unknown) {
      calls.push({ method, path, body });
      return reply as T;
    },
  };
  return { calls, api: createCatalogApi(client) };
}

test.describe("catalog api", () => {
  test("reads status and refreshes discovery per organization", async () => {
    const status = { catalogue_revision: 2, default_model: "fast", publication_state: "CURRENT" };
    const first = recorder(status);
    expect(await first.api.status("org/1")).toEqual(status);
    expect(first.calls[0]).toMatchObject({ method: "GET", path: "/forge/v1/orgs/org%2F1/gateway/catalogue/status" });
    const discovery = { gateway_revision: 3, model_ids: ["a"], capability_state: "unknown", verification: "unverified" };
    const second = recorder(discovery);
    expect(await second.api.refresh("o1")).toEqual(discovery);
    expect(second.calls[0]).toMatchObject({ method: "POST", path: "/forge/v1/orgs/o1/gateway/catalogue/refresh" });
  });

  test("publishes aliases with both expected revisions and an operation id", async () => {
    const { api, calls } = recorder({ revision: 1, default_model: "fast", models: ["fast"] });
    await api.publish("o1", {
      aliases: { fast: "gpt-4o-mini" },
      defaultAlias: "fast",
      expectedCatalogueRevision: 0,
      expectedGatewayRevision: 3,
      operationId: "11111111-1111-4111-8111-111111111111",
    });
    expect(calls[0]).toEqual({
      method: "POST",
      path: "/forge/v1/orgs/o1/models/publish",
      body: {
        operation_id: "11111111-1111-4111-8111-111111111111",
        expected_catalogue_revision: 0,
        expected_gateway_revision: 3,
        aliases: { fast: "gpt-4o-mini" },
        default_alias: "fast",
      },
    });
  });

  test("the published aliases are the ids a member sees", async () => {
    const { api, calls } = recorder({ default_model: "fast", revision: 1, models: [{ id: "fast" }, { id: "deep" }] });
    expect(await api.published("o1")).toEqual({ defaultModel: "fast", aliases: ["fast", "deep"] });
    expect(calls[0]).toMatchObject({ method: "GET", path: "/forge/v1/orgs/o1/models" });
  });
});

test.describe("alias suggestions", () => {
  test("valid ids are kept, others are normalised into the alias grammar", () => {
    expect(suggestAlias("gpt-4o")).toBe("gpt-4o");
    expect(suggestAlias("Anthropic/Claude 3.5")).toBe("anthropic-claude-3-5");
    expect(suggestAlias("4o-mini")).toBe("m-4o-mini");
    expect(suggestAlias("x".repeat(80))).toHaveLength(64);
  });
});

test.describe("selection validation", () => {
  const rows = (...spec: Array<[string, boolean, string]>): Row[] =>
    spec.map(([upstream, selected, alias]) => ({ upstream, selected, alias }));

  test("builds the alias mapping and default from the selected rows only", () => {
    const result = validateSelection(rows(["gpt-4o", true, "smart"], ["gpt-4o-mini", true, "fast"], ["old", false, "old"]), "gpt-4o-mini");
    expect(result).toEqual({ ok: true, aliases: { smart: "gpt-4o", fast: "gpt-4o-mini" }, defaultAlias: "fast" });
  });

  test("reports each problem without leaking server detail", () => {
    expect(validateSelection(rows(["a", false, "a"]), "a")).toEqual({ ok: false, problems: ["Select at least one model."] });
    const bad = validateSelection(rows(["a", true, "Bad Alias"], ["b", true, "dup"], ["c", true, "dup"]), "b");
    expect(bad).toEqual({
      ok: false,
      problems: [
        'Alias "Bad Alias" must start with a letter and use only lowercase letters, digits, "-" and "_".',
        'Alias "dup" is used more than once.',
      ],
    });
    expect(validateSelection(rows(["a", true, "a"], ["b", false, "b"]), "b")).toEqual({
      ok: false,
      problems: ["Choose a default model."],
    });
  });

  test("the default follows the first selected row when the chosen one is dropped", () => {
    const list = rows(["a", false, "a"], ["b", true, "b"], ["c", true, "c"]);
    expect(effectiveDefault(list, "c")).toBe("c");
    expect(effectiveDefault(list, "a")).toBe("b");
    expect(effectiveDefault(rows(["a", false, "a"]), "a")).toBe("");
  });

  test("initial rows select every discovered model with a suggested alias", () => {
    expect(initialRows(["gpt-4o", "4o-mini"])).toEqual([
      { upstream: "gpt-4o", selected: true, alias: "gpt-4o" },
      { upstream: "4o-mini", selected: true, alias: "m-4o-mini" },
    ]);
  });
});

test.describe("catalog messages", () => {
  test("conflicts, rejections and outages are fixed, redacted messages", () => {
    expect(describeCatalogFailure(new ApiError(409, "REVISION_CONFLICT", "x"), "publish")).toBe(
      "The catalog or gateway changed since the models were refreshed. Refresh the models and try again.",
    );
    expect(describeCatalogFailure(new ApiError(409, "MODEL_NOT_ALLOWED", "x"), "publish")).toBe(
      "One or more selected models are not allowed by the platform for this company. Refresh the models and choose from the allowed ones.",
    );
    expect(describeCatalogFailure(new ApiError(409, "MODEL_NOT_ALLOWED", "x"), "refresh")).not.toContain("not allowed by the platform");
    expect(describeCatalogFailure(new ApiError(422, "INVALID_REQUEST", "x"), "publish")).toBe(
      "The selection was not accepted. Refresh the models, then check the aliases.",
    );
    expect(describeCatalogFailure(new ApiError(503, "SERVICE_UNAVAILABLE", "x"), "refresh")).toBe(
      "The gateway could not be reached. Check the gateway settings, then try again.",
    );
    expect(describeCatalogFailure(new Error("x"), "load")).toBe("The catalog could not be loaded. Try again.");
    expect(describeCatalogFailure(new Error("x"), "publish")).toBe("The catalog could not be published. Try again.");
  });

  test("publication states have plain labels", () => {
    expect(publicationLabel("CURRENT")).toBe("Published");
    expect(publicationLabel("UNPUBLISHED")).toBe("Not published");
    expect(publicationLabel("STALE_GATEWAY")).toBe("Gateway changed since publishing");
  });
});
