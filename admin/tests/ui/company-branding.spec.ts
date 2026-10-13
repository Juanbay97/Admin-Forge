import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, ORG_A, expect, expectAccessible, expectNoHorizontalScroll, installBackend, test, viewports } from "./support";

async function open(page: Page, adminUrl: string, view: "Branding") {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: view }).click();
  await expect(page.getByRole("heading", { level: 1, name: view })).toBeVisible();
}

// The branding previews sample the CLIENT palette (accent only guaranteed 3:1), so they are not part of the UI contrast contract.
const PREVIEWS = { exclude: ['[aria-label$="preview"]'] };

async function everyViewport(page: Page, options = {}) {
  for (const viewport of Object.values(viewports)) {
    await page.setViewportSize(viewport);
    await expectNoHorizontalScroll(page);
    await expectAccessible(page, options);
  }
}

test.describe("branding", () => {
  test("reset is confirmed in an alert dialog that starts on Cancel", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Branding");
    await page.getByRole("button", { name: "Reset to default" }).click();
    const confirm = page.getByRole("alertdialog", { name: "Reset branding?" });
    await expect(confirm).toBeVisible();
    await expect(confirm.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(confirm).toBeHidden();
    expect(api.branding(ORG_A)?.revision).toBe(0);
  });

  test("the editor and the previews are separate cards and the form fits a phone", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Branding");
    await expect(page.getByRole("region", { name: "Brand editor" })).toBeVisible();
    await page.setViewportSize(viewports.mobile);
    await expectNoHorizontalScroll(page);
  });

  test("is accessible at every viewport", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await open(page, adminUrl, "Branding");
    await expect(page.getByRole("region", { name: "Brand editor" })).toBeVisible();
    await everyViewport(page, PREVIEWS);
  });
});