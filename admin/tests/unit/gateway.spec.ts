import { expect, test } from "@playwright/test";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createGatewayApi, type Gateway } from "../../src/api/gateway";
import { chooseEndpoint, describeGatewayFailure, gatewayStateLabel } from "../../src/gateway/model";

const PROD = "https://ia.prometheonlab.com";
const LOCAL = "http://127.0.0.1:3413";

function recorder(reply: unknown) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const client: ApiClient = {
    async request<T>(method: string, path: string, body?: unknown) {
      calls.push({ method, path, body });
      return reply as T;
    },
  };
  return { calls, api: createGatewayApi(client) };
}

const gateway = (overrides: Partial<Gateway> = {}): Gateway => ({
  status: "NOT_CONFIGURED",
  revision: 0,
  endpoint: PROD,
  allowed_endpoints: [PROD, LOCAL],
  ...overrides,
});

test.describe("gateway api", () => {
  test("reads the gateway of one organization", async () => {
    const { api, calls } = recorder(gateway());
    expect(await api.get("org/1")).toEqual(gateway());
    expect(calls).toEqual([{ method: "GET", path: "/forge/v1/orgs/org%2F1/gateway", body: undefined }]);
  });

  test("saves the key with the expected revision and chosen endpoint", async () => {
    const saved = { status: "SAVED_UNVERIFIED", revision: 4, endpoint: LOCAL };
    const { api, calls } = recorder(saved);
    expect(await api.save("o1", { endpoint: LOCAL, apiKey: "sk-test", expectedRevision: 3 })).toEqual(saved);
    expect(calls[0]).toEqual({
      method: "PUT",
      path: "/forge/v1/orgs/o1/gateway",
      body: { expected_revision: 3, api_key: "sk-test", endpoint: LOCAL },
    });
  });
});

test.describe("gateway model", () => {
  test("the saved key is reported as configured, never revealed", () => {
    expect(gatewayStateLabel("SAVED_UNVERIFIED")).toBe("Configured");
    expect(gatewayStateLabel("NOT_CONFIGURED")).toBe("Not configured");
  });

  test("the current endpoint is preselected only when it is allow-listed", () => {
    expect(chooseEndpoint(gateway({ endpoint: LOCAL }))).toBe(LOCAL);
    expect(chooseEndpoint(gateway({ endpoint: "https://elsewhere.example" }))).toBe(PROD);
    expect(chooseEndpoint(gateway({ allowed_endpoints: [] }))).toBe("");
  });

  test("failures are fixed, redacted messages", () => {
    expect(describeGatewayFailure(new ApiError(409, "REVISION_CONFLICT", "detail"), "save")).toBe(
      "The gateway configuration was changed by someone else. Reload to see the latest version; nothing was overwritten.",
    );
    expect(describeGatewayFailure(new ApiError(422, "INVALID_REQUEST", "sk-leaky"), "save")).toBe(
      "The base URL or key was not accepted. Check them and try again.",
    );
    expect(describeGatewayFailure(new ApiError(503, "SERVICE_UNAVAILABLE", "x"), "save")).toBe(
      "The key could not be saved. Try again.",
    );
    expect(describeGatewayFailure(new Error("boom"), "load")).toBe("The gateway settings could not be loaded. Try again.");
  });
});
