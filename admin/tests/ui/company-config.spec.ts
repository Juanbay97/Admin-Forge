import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, ORG_A, expect, expectAccessible, expectNoHorizontalScroll, installBackend, test, viewports } from "./support";

async function open(page: Page, adminUrl: string, view: "Gateway" | "Catalog") {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: view }).click();
  await expect(page.getByRole("heading", { level: 1, name: view })).toBeVisible();
}

async function everyViewport(page: Page, options = {}) {
  for (const viewport of Object.values(viewports)) {
    await page.setViewportSize(viewport);
    await expectNoHorizontalScroll(page);
    await expectAccessible(page, options);
  }
}

test.describe("gateway", () => {
  test("summarises the state and keeps the key write-only", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Gateway");
    const summary = page.getByRole("region", { name: "Gateway status" });
    await expect(summary).toContainText("Not configured");
    await expect(summary).toContainText("Revision 0");
    await expect(page.getByText("Write-only: it is never shown again once saved.")).toBeVisible();
    await expect(page.getByLabel("API key")).toHaveAttribute("type", "password");
    await expect(page.getByLabel("API key")).toHaveAttribute("autocomplete", "off");
  });

  test("a conflict is explained inline on the field group and offers a reload", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Gateway");
    api.bumpGateway(ORG_A);
    await page.getByLabel("API key").fill("sk-test-key");
    await page.getByRole("button", { name: "Save key" }).click();
    await expect(page.getByRole("alert")).toContainText("changed by someone else");
    await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
    await expect(page.getByLabel("API key")).toHaveValue("");
  });

  test("is accessible at every viewport", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Gateway");
    await expect(page.getByRole("region", { name: "Gateway status" })).toBeVisible();
    await everyViewport(page);
  });
});

test.describe("catalog", () => {
  test("an unpublished catalog says so with an empty state instead of a bare sentence", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Catalog");
    const summary = page.getByRole("region", { name: "Catalog status" });
    await expect(summary).toContainText("Not published");
    await expect(summary).toContainText("Catalog revision 0");
    await expect(page.getByRole("heading", { name: "No aliases are published." })).toBeVisible();
  });

  test("the model mapping is a named table with one row per discovered model", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Catalog");
    await page.getByRole("button", { name: "Refresh models" }).click();
    const table = page.getByRole("table", { name: "Model mapping" });
    await expect(table.locator("tbody tr")).toHaveCount(3);
    await expect(table.getByRole("columnheader")).toHaveText(["Publish", "Upstream model", "Alias", "Default"]);
    await expect(page.getByRole("button", { name: "Publish catalog" })).toBeEnabled();
  });

  test("is accessible at every viewport, including the mapping", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Catalog");
    await page.getByRole("button", { name: "Refresh models" }).click();
    await expect(page.getByRole("table", { name: "Model mapping" })).toBeVisible();
    await everyViewport(page);
  });
});
