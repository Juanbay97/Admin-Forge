import { expect, test } from "@playwright/test";
import { ApiError, type ApiClient } from "../../src/api/client";
import { createInstallerApi, parseInstallerConfig } from "../../src/api/installer";
import { configFile, stampedFilename } from "../../src/portal/download";

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
  test("the stamped download asks for the chosen company and names the file for it", async () => {
    const asked: string[] = [];
    const download = { download: async (path: string) => { asked.push(path); return { blob: new Blob(["MZ"]), disposition: 'attachment; filename="Prometheon-Forge-Setup-acme.exe"' }; } };
    const api = createInstallerApi({ request: async () => ({}) as never }, download);
    const file = await api.stamped("11111111-1111-4111-8111-111111111111", "acme");
    expect(asked).toEqual(["/forge/v1/downloads/company?org=11111111-1111-4111-8111-111111111111"]);
    expect(file.filename).toBe("Prometheon-Forge-Setup-acme.exe");
    expect(await file.blob.text()).toBe("MZ");
  });
  test("the saved file name is the server's when it is the stamped pattern, else built from the company code, else plain", () => {
    expect(stampedFilename('attachment; filename="Prometheon-Forge-Setup-org-a.exe"', "ignored")).toBe("Prometheon-Forge-Setup-org-a.exe");
    expect(stampedFilename(null, "acme")).toBe("Prometheon-Forge-Setup-acme.exe");
    for (const hostile of ['attachment; filename="..\\evil.exe"', 'attachment; filename="a/b.exe"', 'attachment; filename="Prometheon-Forge-Setup-A.exe"', "attachment", ""]) {
      expect(stampedFilename(hostile, "acme"), hostile).toBe("Prometheon-Forge-Setup-acme.exe");
    }
    for (const code of [null, "", "Acme", "../x", "-a", "a".repeat(64)]) expect(stampedFilename(null, code), String(code)).toBe("Prometheon-Forge-Setup.exe");
  });
  test("without a download client the stamped download is refused, not faked", async () => {
    await expect(createInstallerApi({ request: async () => ({}) as never }).stamped("x", "acme")).rejects.toBeInstanceOf(ApiError);
  });
  test("the file is pretty JSON with the fixed name", () => {
    const file = configFile(parseInstallerConfig(config)!);
    expect(file.filename).toBe("forge-install.json");
    expect(JSON.parse(file.text)).toEqual(config);
    expect(file.text.endsWith("\n")).toBe(true);
  });
});
