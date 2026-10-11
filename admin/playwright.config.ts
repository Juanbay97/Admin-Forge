import { defineConfig } from "@playwright/test";

// Real end-to-end layer: system Chrome against the running local MVP stack (control plane serving the
// production bundle + fake gateway). `scripts\admin-e2e.ps1` starts the owned stack and exports the
// origin and the credentials file; this config never starts or stops anything itself.
const adminUrl = process.env.FORGE_E2E_ADMIN_URL;
if (!adminUrl) {
  throw new Error("FORGE_E2E_ADMIN_URL is not set: run scripts\\admin-e2e.ps1 (it starts the owned local stack).");
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  outputDir: "./test-results/e2e",
  use: { baseURL: adminUrl, channel: "chrome", headless: true },
});
