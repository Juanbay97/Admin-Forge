import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { ACME, GLOBEX, OWNER, installPlatform, newWorld, type World } from "./platformSupport";

const ACTOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function many(): World {
  const world = newWorld();
  world.audit = Array.from({ length: 70 }, (_, index) => ({
    id: index + 1,
    actor_id: ACTOR,
    action: index % 3 === 0 ? "company.suspended" : index % 3 === 1 ? "model_price.set" : "company.branding_saved",
    organization_id: index % 3 === 1 ? null : index % 2 === 0 ? ACME : GLOBEX,
    recorded_at: new Date(Date.UTC(2026, 9, 1, 0, index)).toISOString(),
  }));
  return world;
}

async function open(page: Page, adminUrl: string, path: string, world = many()) {
  world.mfa.verified = true;
  const backend = await installPlatform(page, world);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  return backend;
}

test.describe("audit log", () => {
  test("is read-only, newest first, with relative and absolute times", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/audit");
    const table = page.getByRole("table", { name: "Audit log" });
    await expect(table.getByRole("row")).toHaveCount(51); // header + the first page of 50
    const first = table.getByRole("row").nth(1);
    await expect(first).toContainText("Oct 1, 2026");
    await expect(first.locator("time")).toHaveAttribute("datetime", /2026-10-01T01:09/); // entry 70
    await expect(table.getByRole("button")).toHaveCount(0); // sort buttons aside, nothing here edits
  });

  test("Load more follows the cursor to the older entries", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, "platform/audit");
    await page.getByRole("button", { name: "Load more" }).click();
    await expect(page.getByRole("table", { name: "Audit log" }).getByRole("row")).toHaveCount(71);
    expect(requests.filter((request) => request.path.endsWith("/audit")).map((request) => request.search)).toEqual(["?page=50", "?before=21&page=50"]);
    await expect(page.getByRole("button", { name: "Load more" })).toHaveCount(0);
  });

  test("filters by action and company live in the URL and survive a reload", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/audit");
    await page.getByLabel("Action").selectOption("model_price.set");
    await expect(page).toHaveURL(/action=model_price.set/);
    const rows = page.getByRole("table", { name: "Audit log" }).getByRole("row");
    await expect(rows.nth(1)).toContainText("Model price set");
    for (const text of await rows.allTextContents()) if (text.includes("suspended")) throw new Error("a filtered-out action is listed");
    await page.reload();
    await page.getByLabel("Email").fill(OWNER.email);
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByLabel("Action")).toHaveValue("model_price.set");
    await page.getByLabel("Action").selectOption("");
    await page.getByLabel("Company").selectOption({ label: "Globex" });
    await expect(page).toHaveURL(/company=2222/);
    await expect(page.getByRole("table", { name: "Audit log" }).getByRole("row").nth(1)).toContainText("Globex");
  });

  test("a filter that matches nothing among the loaded entries says so and offers more", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.audit = [{ id: 1, actor_id: ACTOR, action: "company.created", organization_id: ACME, recorded_at: "2026-10-01T00:00:00Z" }];
    await open(page, adminUrl, "platform/audit?action=model_price.set", world);
    await expect(page.getByText("No matching events")).toBeVisible();
  });

  test("is accessible on every viewport, light and dark", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform/audit");
    await expect(page.getByRole("table", { name: "Audit log" })).toBeVisible();
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

test.describe("command palette", () => {
  test("jumps to a company by name or code, and to a page", async ({ page, adminUrl }) => {
    await open(page, adminUrl, "platform");
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
    await page.waitForLoadState("networkidle"); // the company list feeds the palette
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Command palette" });
    await palette.getByRole("combobox").fill("glob");
    await expect(palette.getByRole("option", { name: /Globex/ })).toBeVisible();
    await expect(palette.getByRole("option", { name: /Acme/ })).toHaveCount(0);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Globex" })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/platform/companies/${GLOBEX}`));
    await page.keyboard.press("Control+k");
    await page.getByRole("dialog", { name: "Command palette" }).getByRole("combobox").fill("prices");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Model prices" })).toBeVisible();
  });
});