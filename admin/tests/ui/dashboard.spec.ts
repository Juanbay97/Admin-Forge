import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { newPortalWorld, type PortalWorld } from "./portalSupport";
import { joinAndLand } from "./portalSession";

const go = (page: Page, path: string) =>
  page.evaluate((target) => {
    history.pushState(null, "", `/admin${target}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);

function adminWorld(): PortalWorld {
  const world = newPortalWorld();
  world.roles = ["organization_admin", "member"];
  world.memberList = [
    { id: "m1", email: "alex@acme.test", display_name: "Alex Admin", status: "active", roles: ["organization_admin"], departments: [{ id: "d-legal", name: "Legal" }] },
    { id: "m2", email: "pat@acme.test", display_name: "Pat Member", status: "active", roles: ["member"], departments: [{ id: "d-fin", name: "Finance" }] },
  ];
  world.departments = [{ id: "d-legal", name: "Legal" }, { id: "d-fin", name: "Finance" }];
  return world;
}

async function open(page: Page, adminUrl: string, world = adminWorld()) {
  const backend = await joinAndLand(page, adminUrl, world);
  await go(page, "/company");
  await expect(page.getByRole("region", { name: "Usage" })).toBeVisible();
  return backend;
}

test.describe("company dashboard", () => {
  test("KPIs, top people and the per-person table sorted by cost with share bars", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    const kpis = page.getByRole("region", { name: "Key figures" });
    await expect(kpis.getByText("90K")).toBeVisible(); // Alex 80,000 + Pat 10,000
    await expect(kpis.getByText("$1.05")).toBeVisible();
    await expect(kpis.getByText("2 of 3")).toBeVisible(); // people who used it, of everyone listed
    const table = page.getByRole("table", { name: "People", exact: true });
    const rows = table.getByRole("row");
    await expect(rows.nth(1)).toContainText("Alex Admin"); // highest cost first
    await expect(rows.nth(1)).toContainText("Legal");
    await expect(rows.nth(1)).toContainText("89%");
    await expect(rows.nth(2)).toContainText("Pat Member");
    await expect(rows.nth(3)).toContainText("Sam Suspended");
    await expect(rows.nth(3)).toContainText("Suspended");
    await expect(page.getByRole("figure").filter({ hasText: "Top people by tokens" }).getByTestId("bar-label").first()).toHaveText("Alex Admin");
  });

  test("sorts by name and filters by search and department, all from the keyboard-operable controls", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    const table = page.getByRole("table", { name: "People", exact: true });
    await table.getByRole("button", { name: "Person" }).click();
    await expect(table.getByRole("row").nth(1)).toContainText("Alex Admin");
    await table.getByRole("button", { name: "Person" }).click();
    await expect(table.getByRole("row").nth(1)).toContainText("Sam Suspended");
    await page.getByLabel("Search people").fill("pat");
    await expect(table.getByRole("row")).toHaveCount(2);
    await page.getByLabel("Search people").fill("");
    await page.getByLabel("Department", { exact: true }).selectOption("Finance");
    await expect(table.getByRole("row")).toHaveCount(2);
    await expect(table.getByRole("row").nth(1)).toContainText("Pat Member");
  });

  test("the range is in the URL and the report is requested for the range and the period before it", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl);
    await page.getByRole("button", { name: "7 days" }).click();
    await expect(page).toHaveURL(/days=7/);
    const sevenDays = () => requests.filter((request) => request.path.endsWith("/usage/members")).map((request) => new URLSearchParams(request.search)).filter((params) => (Date.parse(params.get("to")!) - Date.parse(params.get("from")!)) / 86_400_000 === 6);
    await expect.poll(() => sevenDays().length).toBeGreaterThanOrEqual(2);
  });

  test("no usage yet explains how usage starts and points at inviting people", async ({ page, adminUrl }) => {
    const world = adminWorld();
    world.members = (world.members as Array<Record<string, unknown>>).map((row) => ({ ...row, requests: 0, prompt_tokens: 0, completion_tokens: 0, cost_micros: 0, error_requests: 0, estimated_requests: 0 }));
    await open(page, adminUrl, world);
    await expect(page.getByRole("heading", { name: "No usage yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Invite people" })).toHaveAttribute("href", "/admin/company/members");
  });

  test("keeps the departments summary the page always had", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await expect(page.getByRole("region", { name: "Summary" })).toContainText("Departments");
  });

  test("is accessible in light and dark on every viewport", async ({ page, adminUrl }) => {
    await open(page, adminUrl);
    await expect(page.getByRole("table", { name: "People", exact: true })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});