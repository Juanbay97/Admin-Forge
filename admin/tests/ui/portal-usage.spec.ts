import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { newPortalWorld } from "./portalSupport";
import { joinAndLand } from "./portalSession";

const mine = JSON.parse(readFileSync(new URL("../fixtures/portal/usage-me.json", import.meta.url), "utf8")) as Record<string, unknown>;
const go = (page: Page, path: string) =>
  page.evaluate((target) => {
    history.pushState(null, "", `/admin${target}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);

test.describe("portal home", () => {
  test("welcomes the member, points at the app and summarises the last seven days", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.usageMe = mine;
    await joinAndLand(page, adminUrl, world);
    await go(page, "/portal");
    await expect(page.getByRole("heading", { level: 1, name: "Welcome, Nina" })).toBeVisible();
    await expect(page.getByText("You are part of Acme Corp.")).toBeVisible();
    await expect(page.getByText("10K")).toBeVisible();
    await expect(page.getByRole("link", { name: /Download and set up/ })).toHaveAttribute("href", "/admin/portal/download");
    await expect(page.getByRole("link", { name: "See my usage" })).toHaveAttribute("href", "/admin/portal/usage");
    await expect(page.getByRole("navigation", { name: "Sections" }).getByRole("button")).toHaveText(["Home", "Get the app", "My usage"]);
  });

  test("without a usage route the home still works", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await go(page, "/portal");
    await expect(page.getByText("Usage will appear here once the app is in use.")).toBeVisible();
  });

  test("is accessible and fits every viewport", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await go(page, "/portal");
    await expect(page.getByRole("heading", { level: 1, name: "Welcome, Nina" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});

test.describe("my usage", () => {
  test("shows tokens, requests, cost and the prompt/completion split for the range, only from the member's own route", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.usageMe = mine;
    const { requests } = await joinAndLand(page, adminUrl, world);
    await go(page, "/portal/usage");
    const kpis = page.getByRole("region", { name: "My usage" });
    await expect(kpis.getByText("10K")).toBeVisible();
    await expect(kpis.getByText("12", { exact: true })).toBeVisible();
    await expect(kpis.getByText("$0.15")).toBeVisible();
    await expect(page.getByRole("figure").filter({ hasText: "Prompt and completion tokens" }).getByTestId("bar-label").first()).toBeVisible();
    expect(requests.filter((request) => request.path.includes("/usage/")).every((request) => request.path.endsWith("/usage/me"))).toBe(true);
    expect(requests.some((request) => request.path.includes("/usage/members"))).toBe(false);
  });

  test("the range is in the URL and drives the request", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.usageMe = mine;
    const { requests } = await joinAndLand(page, adminUrl, world);
    await go(page, "/portal/usage");
    await page.getByRole("button", { name: "90 days" }).click();
    await expect(page).toHaveURL(/days=90/);
    await expect.poll(() => requests.filter((request) => request.path.endsWith("/usage/me")).some((request) => { const p = new URLSearchParams(request.search); return (Date.parse(p.get("to")!) - Date.parse(p.get("from")!)) / 86_400_000 === 89; })).toBe(true);
  });

  test("no usage yet suggests the app", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.usageMe = { ...mine, requests: 0, prompt_tokens: 0, completion_tokens: 0, cost_micros: 0, estimated_requests: 0 };
    await joinAndLand(page, adminUrl, world);
    await go(page, "/portal/usage");
    await expect(page.getByText("No usage yet")).toBeVisible();
    await expect(page.getByRole("link", { name: "Get the app" }).first()).toBeVisible();
  });

  test("a server without the route says reporting is not available yet instead of failing", async ({ page, adminUrl }) => {
    await joinAndLand(page, adminUrl);
    await go(page, "/portal/usage");
    await expect(page.getByText("Usage reporting is not available yet")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("is accessible and fits every viewport", async ({ page, adminUrl }) => {
    const world = newPortalWorld();
    world.usageMe = mine;
    await joinAndLand(page, adminUrl, world);
    await go(page, "/portal/usage");
    await expect(page.getByRole("region", { name: "My usage" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});