import { ADMIN_BACKEND, expect, expectAccessible, expectNoHorizontalScroll, installBackend, test, viewports } from "./support";
import { GOOD_CODE, OWNER, installPlatform, newWorld } from "./platformSupport";

async function signIn(page: import("@playwright/test").Page, adminUrl: string, navigate = true) {
  if (navigate) await page.goto(adminUrl);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.describe("platform console access", () => {
  test("a company administrator is denied the platform area", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl + "platform");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
    await expect(page.getByText("Platform console")).toHaveCount(0);
  });

  test("an owner lands in the console with the persistent badge, their email and the five pages", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.mfa.verified = true;
    await installPlatform(page, world);
    await signIn(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
    await expect(page.getByText("Platform console").first()).toBeVisible();
    await page.getByRole("button", { name: "Account menu" }).click();
    await expect(page.getByText(OWNER.email)).toBeVisible();
    await page.keyboard.press("Escape");
    const nav = page.getByRole("navigation", { name: "Sections" });
    for (const label of ["Overview", "Companies", "Gateway keys", "Prices", "Audit log"]) await expect(nav.getByRole("button", { name: label })).toBeVisible();
  });

  test("the console wears the fixed Prometheon theme and supports dark mode, accessibly", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.mfa.verified = true;
    await installPlatform(page, world);
    await page.goto(adminUrl);
    await page.evaluate(() => document.documentElement.style.setProperty("--brand-primary", "#ff0000")); // a company theme left behind
    await signIn(page, adminUrl, false);
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.style.getPropertyValue("--brand-primary"))).not.toBe("#ff0000");
    await expectAccessible(page);
    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    expect(await page.evaluate(() => document.documentElement.dataset.mode)).toBe("dark");
    await expectAccessible(page);
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
    }
  });

  test("thirty idle minutes sign the owner out with a notice", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.mfa.verified = true;
    await page.clock.install();
    await installPlatform(page, world);
    await signIn(page, adminUrl);
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
    await page.clock.fastForward("30:01");
    await expect(page.getByText("Signed out for inactivity.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });
});

void GOOD_CODE;