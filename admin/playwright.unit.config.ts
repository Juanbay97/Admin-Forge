import { defineConfig } from "@playwright/test";

// Two layers share one runner: "unit" is browser-free logic; "ui" drives the production
// bundle in the system Chrome against a mocked same-origin API (no downloaded browsers).
export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  projects: [
    { name: "unit", testDir: "./tests/unit" },
    { name: "ui", testDir: "./tests/ui", use: { channel: "chrome", headless: true } },
  ],
});
