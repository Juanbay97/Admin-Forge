import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { ACME, GLOBEX, OWNER, installPlatform, newWorld } from "./platformSupport";

const SECOND = "66666666-6666-4666-8666-666666666666";

function world() {
  const value = newWorld();
  value.keys = [...value.keys, { id: SECOND, label: "Backup", origin: "https://gateway.example.test", revision: 1, status: "active", has_key: true, hint: "9z9z", companies: 0 }];
  return value;
}

async function open(page: Page, adminUrl: string, path: string, state = world()) {
  state.mfa.verified = true;
  const backend = await installPlatform(page, state);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  return backend;
}

test.describe("company branding tab", () => {
  test("edits and saves with the revision, reports a conflict and resets with a confirmation", async ({ page, adminUrl }) => {
    const { requests, world: state } = await open(page, adminUrl, `platform/companies/${ACME}?tab=branding`);
    await expect(page.getByRole("tab", { name: "Branding", selected: true })).toBeVisible();
    await expect(page.getByText("Revision 0")).toBeVisible();
    await page.getByLabel("Product name").fill("Acme Forge");
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByText("Branding saved (revision 1)")).toBeVisible();
    const saved = requests.find((request) => request.method === "PUT" && request.path.endsWith("/branding"));
    expect(saved?.body).toMatchObject({ expectedRevision: 0, branding: { name: "Acme Forge" } });
    expect(await page.evaluate(() => document.documentElement.style.getPropertyValue("--brand-primary"))).not.toBe("");
    (state.branding[ACME] as { revision: number }).revision = 7; // someone else saved
    await page.getByLabel("Product name").fill("Acme Two");
    await page.getByRole("button", { name: "Save branding" }).click();
    await expect(page.getByRole("alert")).toContainText("changed by another administrator");
    await page.getByRole("button", { name: "Reload branding" }).click();
    await expect(page.getByText("Revision 7")).toBeVisible();
    await page.getByRole("button", { name: "Reset to default" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Confirm reset" }).click();
    await expect(page.getByText(/reset to the Prometheon default \(revision 8\)/i)).toBeVisible();
  });

  test("the console keeps its own theme while a company's branding is edited", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}?tab=branding`);
    const before = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--brand-primary"));
    await page.getByLabel("Primary color", { exact: true }).fill("#7C3AED");
    await expect(page.getByRole("button", { name: "Save branding" })).toBeEnabled();
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--brand-primary"))).toBe(before);
  });

  test("has no logo upload (the platform API has none) and is accessible", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}?tab=branding`);
    await expect(page.getByText("Logos (PNG or WebP")).toHaveCount(0);
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page, { exclude: ['[aria-label$="preview"]'] });
    }
  });
});

test.describe("company keys tab", () => {
  test("lists assigned keys by label and last four only, adds from the pool, reorders and saves one PUT", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, `platform/companies/${ACME}?tab=keys`);
    const list = page.getByRole("list", { name: "Assigned keys" });
    await expect(list.locator("span.font-medium", { hasText: "Primary" })).toBeVisible();
    await expect(list.getByText("••••a1b2")).toBeVisible();
    await page.getByLabel("Add a key from the pool").selectOption({ label: "Backup · ••••9z9z" });
    await page.getByRole("button", { name: "Add key" }).click();
    await expect(list.getByRole("listitem")).toHaveCount(2);
    await page.getByRole("button", { name: "Move Backup up" }).click();
    await expect(list.getByRole("listitem").first()).toContainText("Backup");
    await page.getByRole("button", { name: "Save keys" }).click();
    await expect(page.getByText("Gateway keys saved")).toBeVisible();
    const puts = requests.filter((request) => request.method === "PUT" && request.path.endsWith("/gateway-keys"));
    expect(puts).toHaveLength(1);
    expect(puts[0]?.body).toEqual({ keys: [{ key_id: SECOND, priority: 1, active: true }, { key_id: "55555555-5555-4555-8555-555555555555", priority: 2, active: true }] });
    expect(await page.content()).not.toMatch(/sk-[A-Za-z0-9]{8,}/);
  });

  test("removing the last key warns that the company loses gateway access", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}?tab=keys`);
    await page.getByRole("button", { name: "Remove Primary" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("lose access to the gateway");
    await dialog.getByRole("button", { name: "Remove key" }).click();
    await expect(page.getByText("No keys assigned")).toBeVisible();
  });

  test("a key can be switched off for the company without removing it", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, `platform/companies/${ACME}?tab=keys`);
    await page.getByRole("switch", { name: "Primary active" }).click();
    await page.getByRole("button", { name: "Save keys" }).click();
    await expect(page.getByText("Gateway keys saved")).toBeVisible();
    expect(requests.find((request) => request.method === "PUT")?.body).toMatchObject({ keys: [{ active: false }] });
  });

  test("a suspended company's tabs are read-only", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${GLOBEX}?tab=keys`);
    await expect(page.getByText("This company is suspended")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save keys" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Add key" })).toHaveCount(0);
  });

  test("is accessible on every viewport, light and dark", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}?tab=keys`);
    await expect(page.getByRole("list", { name: "Assigned keys" })).toBeVisible();
    for (const dark of [false, true]) {
      if (dark) await page.getByRole("button", { name: "Switch to dark mode" }).click();
      for (const size of Object.values(viewports)) {
        await page.setViewportSize(size);
        await expectNoHorizontalScroll(page);
        await expectAccessible(page);
      }
    }
  });
});

test.describe("company models tab", () => {
  test("shows the allowed models with their prices, adds, removes and saves one PUT", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, `platform/companies/${ACME}?tab=models`);
    const table = page.getByRole("table", { name: "Allowed models" });
    await expect(table.getByRole("row", { name: /gpt-4o\b/ }).getByText("$2.50")).toBeVisible();
    await expect(table.getByRole("row", { name: /gpt-4o\b/ }).getByText("$10.00")).toBeVisible();
    await expect(table.getByRole("row", { name: /gpt-4o-mini/ }).getByText("No price").first()).toBeVisible();
    await page.getByLabel("Add a model").fill("claude-3-5-sonnet");
    await page.getByRole("button", { name: "Add model" }).click();
    await page.getByRole("button", { name: "Remove gpt-4o-mini" }).click();
    await page.getByRole("button", { name: "Save models" }).click();
    await expect(page.getByText("Allowed models saved")).toBeVisible();
    const puts = requests.filter((request) => request.method === "PUT" && request.path.endsWith("/model-access"));
    expect(puts).toHaveLength(1);
    expect(puts[0]?.body).toEqual({ models: ["gpt-4o", "claude-3-5-sonnet"] });
  });

  test("a suspended company's model list is read-only", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${GLOBEX}?tab=models`);
    await expect(page.getByText("This company is suspended")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save models" })).toHaveCount(0);
    await expect(page.getByLabel("Add a model")).toHaveCount(0);
  });

  test("is accessible on every viewport", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}?tab=models`);
    await expect(page.getByRole("table", { name: "Allowed models" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});