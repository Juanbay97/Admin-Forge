import type { Page } from "@playwright/test";
import { ADMIN_BACKEND, expect, expectAccessible, expectNoHorizontalScroll, installBackend, test, viewports } from "./support";

async function signIn(page: Page, email = "admin@example.com") {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
}

const pathOf = (page: Page) => new URL(page.url()).pathname;

test.describe("router and guards", () => {
  test("the root redirects an organization administrator to the company area", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company");
  });

  test("a deep link survives sign-in: the URL is the return target and nothing is stored", async ({ page, origin }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(`${origin}/admin/company/members`);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company/members");
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company/members");
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).toBe("{}");
  });

  test("navigation changes the URL and a reload of a deep link asks for sign-in again", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page);
    await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Gateway" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Gateway" })).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company/gateway");
    await page.reload();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company/gateway");
  });

  test("an unregistered area is not found inside the shell and makes no platform call", async ({ page, origin }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(`${origin}/admin/company`);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await page.goto(`${origin}/admin/platform`);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Not found" })).toBeVisible();
    expect(api.requests.filter((request) => request.path.includes("/platform"))).toEqual([]);
  });

  test("an unknown path under the shell renders Not found inside the chrome", async ({ page, origin }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(`${origin}/admin/company/nothing-here`);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Not found" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Sections" })).toBeVisible();
  });
});

test.describe("session expiry", () => {
  test("a 401 returns to the same URL with a notice and sign-in resumes there", async ({ page, adminUrl }) => {
    const api = await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    api.expire();
    await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Members" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await expect(page.getByText("Your session expired. Sign in again to continue.")).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company/members");
    api.renew();
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company/members");
  });

  test("signing out clears the session without an expiry notice", async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await expect(page.getByText(/session expired/i)).toHaveCount(0);
  });
});

test.describe("shell chrome", () => {
  test.beforeEach(async ({ page, adminUrl }) => {
    await installBackend(page, ADMIN_BACKEND);
    await page.goto(adminUrl);
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Org A" })).toBeVisible();
  });

  test("the first Tab stops on the skip link and activating it focuses the main landmark", async ({ page }) => {
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("main#main")).toBeFocused();
  });

  test("the sidebar marks the current page and breadcrumbs name where you are", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    await nav.getByRole("button", { name: "Members" }).click();
    await expect(nav.getByRole("button", { name: "Members" })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("button", { name: "Overview" })).not.toHaveAttribute("aria-current", "page");
    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs).toContainText("Company");
    await expect(crumbs.getByText("Members")).toHaveAttribute("aria-current", "page");
  });

  test("the sidebar collapses to icons and expands again", async ({ page }) => {
    const sidebar = page.locator("aside");
    expect((await sidebar.boundingBox())!.width).toBe(256);
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    expect((await sidebar.boundingBox())!.width).toBe(64);
    await expect(page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Members" })).toBeVisible();
    await page.getByRole("button", { name: "Expand sidebar" }).click();
    expect((await sidebar.boundingBox())!.width).toBe(256);
  });

  test("Ctrl+K opens the command palette, filters the area's pages, navigates on Enter and restores focus on Escape", async ({ page }) => {
    await page.getByRole("button", { name: "Sign out" }).focus();
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Command palette" });
    await expect(palette).toBeVisible();
    await expect(palette.getByRole("option")).toHaveText(["Overview", "Members", "Gateway", "Catalog", "Branding"]);
    await page.keyboard.type("mem");
    await expect(palette.getByRole("option")).toHaveText(["Members"]);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
    expect(pathOf(page)).toBe("/admin/company/members");
    await page.keyboard.press("Control+k");
    await expect(palette).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(palette).toBeHidden();
  });

  test("below 1024px the sidebar becomes a drawer opened from the topbar", async ({ page }) => {
    await page.setViewportSize(viewports.mobile);
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav).toBeHidden();
    await page.getByRole("button", { name: "Open navigation" }).click();
    const drawer = page.getByRole("dialog", { name: "Navigation" });
    await expect(drawer.getByRole("navigation", { name: "Sections" })).toBeVisible();
    await drawer.getByRole("button", { name: "Catalog" }).click();
    await expect(drawer).toBeHidden();
    await expect(page.getByRole("heading", { level: 1, name: "Catalog" })).toBeVisible();
  });

  test("passes axe and fits the viewport on every size and page", async ({ page }) => {
    for (const viewport of Object.values(viewports)) {
      await page.setViewportSize(viewport);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
    await page.setViewportSize(viewports.desktop);
    for (const name of ["Members", "Gateway", "Catalog", "Branding"]) {
      await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name }).click();
      await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
      // The branding previews reproduce the CLIENT palette, whose accent is only guaranteed 3:1 by the server; they are samples, not UI.
      await expectAccessible(page, { exclude: ['[aria-label$="preview"]'] });
    }
  });
});