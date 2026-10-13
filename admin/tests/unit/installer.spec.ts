import { expect, test } from "@playwright/test";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createInstallerApi, parseInstallerConfig } from "../../src/api/installer";
import { configFile } from "../../src/portal/download";

const KEY = { kid: "0123456789abcdef", alg: "Ed25519", public_key: "A".repeat(43), status: "active" };
const config = {
  schema: "forge.installer-config.v1",
  company_code: "acme",
  control_plane_origin: "https://forge.example.test",
  policy_keys: { schema: "forge.capability-keys.v1", keys: [KEY, { ...KEY, kid: "fedcba9876543210", status: "retired" }] },
};

test.describe("installer configuration", () => {
  test("accepts the served shape", () => {
    expect(parseInstallerConfig(config)?.company_code).toBe("acme");
    expect(parseInstallerConfig(config)?.policy_keys.keys).toHaveLength(2);
  });
  test("refuses anything else: schema, code, origin, key shapes and unknown fields", () => {
    const bad = [
      { ...config, schema: "forge.installer-config.v2" },
      { ...config, company_code: "Acme Corp" },
      { ...config, control_plane_origin: "javascript:alert(1)" },
      { ...config, control_plane_origin: "https://forge.example.test/path" },
      { ...config, extra: 1 },
      { ...config, policy_keys: { schema: "forge.capability-keys.v1", keys: [] } },
      { ...config, policy_keys: { schema: "forge.capability-keys.v1", keys: [{ ...KEY, alg: "RS256" }] } },
      { ...config, policy_keys: { schema: "forge.capability-keys.v1", keys: [{ ...KEY, kid: "xyz" }] } },
      { ...config, policy_keys: { schema: "forge.capability-keys.v1", keys: [{ ...KEY, status: "other" }] } },
      null,
      "text",
    ];
    for (const value of bad) expect(parseInstallerConfig(value), JSON.stringify(value)).toBeNull();
  });
  test("the client asks for the chosen company and refuses an unexpected response", async () => {
    const calls: string[] = [];
    const client = (response: unknown): ApiClient => ({ request: async (method, path) => { calls.push(`${method} ${path}`); return response as never; } });
    expect((await createInstallerApi(client(config)).config("11111111-1111-4111-8111-111111111111")).company_code).toBe("acme");
    expect(calls).toEqual(["GET /forge/v1/capabilities/installer-config?org=11111111-1111-4111-8111-111111111111"]);
    await expect(createInstallerApi(client({ nope: true })).config("x")).rejects.toBeInstanceOf(ApiError);
  });
  test("the file is pretty JSON with the fixed name", () => {
    const file = configFile(parseInstallerConfig(config)!);
    expect(file.filename).toBe("forge-install.json");
    expect(JSON.parse(file.text)).toEqual(config);
    expect(file.text.endsWith("\n")).toBe(true);
  });
});
