import { expect, test } from "@playwright/test";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createGatewayApi, type Gateway } from "../../src/api/gateway";
import { describeGatewayFailure, gatewayStateLabel } from "../../src/gateway/model";

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
  endpoint: "",
  allowed_endpoints: [],
  ...overrides,
});

test.describe("gateway api", () => {
  test("reads the gateway status of one organization and never writes", async () => {
    const { api, calls } = recorder(gateway({ status: "SAVED_UNVERIFIED", revision: 2 }));
    expect(await api.get("org/1")).toEqual(gateway({ status: "SAVED_UNVERIFIED", revision: 2 }));
    expect(calls).toEqual([{ method: "GET", path: "/forge/v1/orgs/org%2F1/gateway", body: undefined }]);
    expect("save" in api).toBe(false);
  });
});

test.describe("gateway model", () => {
  test("the platform key is reported as configured, never revealed", () => {
    expect(gatewayStateLabel("SAVED_UNVERIFIED")).toBe("Configured");
    expect(gatewayStateLabel("NOT_CONFIGURED")).toBe("Not configured");
  });

  test("failures are fixed, redacted messages", () => {
    expect(describeGatewayFailure(new ApiError(503, "SERVICE_UNAVAILABLE", "sk-leaky"))).toBe(
      "The gateway settings could not be loaded. Try again.",
    );
    expect(describeGatewayFailure(new Error("boom"))).toBe("The gateway settings could not be loaded. Try again.");
  });
});
