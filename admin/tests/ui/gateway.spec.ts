import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, ORG_A, ORG_B, expect, installBackend, test } from "./support";

async function openGateway(page: Page, adminUrl: string, email = "admin@example.com") {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  if (email === "multi@example.com") await page.getByLabel("Organization").selectOption({ label: "Org A" });
  await page.getByRole("button", { name: "Gateway" }).click();
}

test.describe("gateway status (read-only)", () => {
  test("shows the status and the usable platform keys, with nothing to edit", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Gateway" })).toBeVisible();
    await expect(page.getByText("Not configured")).toBeVisible();
    await expect(page.getByText("Usable platform keys: 0")).toBeVisible();
    await expect(page.getByText("The gateway key is managed by the platform.")).toBeVisible();
    await expect(page.getByLabel("API key")).toHaveCount(0);
    await expect(page.getByLabel("Gateway base URL")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Save key" })).toHaveCount(0);
    expect(api.requests.filter((request) => request.method !== "GET" && request.path.endsWith("/gateway"))).toEqual([]);
  });

  test("a stale organization renders the generic not-found", async ({ page, adminUrl }) => {
    await installBackend(page, { ...ADMIN_BACKEND, gateways: {} });
    await openGateway(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await expect(page.getByText("Usable platform keys")).toHaveCount(0);
  });

  test("switching organizations clears the gateway before the next loads", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await openGateway(page, adminUrl, "multi@example.com");
    await expect(page.getByText("Usable platform keys: 0")).toBeVisible();
    api.hold(ORG_B);
    await page.getByLabel("Organization").selectOption({ label: "Org B" });
    await expect(page.getByRole("status")).toHaveText("Loading gateway...");
    await expect(page.getByText("Usable platform keys: 0")).toHaveCount(0);
    api.letThrough(ORG_B);
    await expect(page.getByText("Usable platform keys: 2")).toBeVisible();
    await expect(page.getByText("Configured", { exact: true })).toBeVisible();
    expect(api.stored(ORG_A)?.savedKey).toBeUndefined();
  });
});
