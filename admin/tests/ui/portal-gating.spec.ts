import type { Page } from "@playwright/test";
import { expect, test } from "./support";
import { newPortalWorld } from "./portalSupport";
import { joinAndLand } from "./portalSession";

/** Client-side navigation keeps the in-memory session (a page load would sign in again). */
const go = (page: Page, path: string) =>
  page.evaluate((target) => {
    history.pushState(null, "", `/admin${target}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);

test.describe("portal gating", () => {
  test("the admin root sends a plain member to the portal", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await go(page, "/");
    await expect(page).toHaveURL(/\/admin\/portal/);
    await expect(page.getByRole("navigation", { name: "Sections" }).getByRole("button")).toHaveText(["Get the app"]);
  });

  test("the company and platform areas are closed to a member, and no company data is requested", async ({ page, adminUrl }) => {
    const { requests } = await joinAndLand(page, adminUrl);
    await go(page, "/company/members");
    await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
    await go(page, "/platform");
    await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
    expect(requests.filter((request) => /\/members|\/usage\//.test(request.path))).toEqual([]);
  });

  test("a company administrator keeps the company area as home but may open the portal", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.roles = ["organization_admin", "member"];
    await joinAndLand(page, adminUrl, world);
    await go(page, "/");
    await expect(page).toHaveURL(/\/admin\/company/);
    await go(page, "/portal/download");
    await expect(page.getByRole("heading", { level: 1, name: "Get the app" })).toBeVisible();
  });
});