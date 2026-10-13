import { expect, expectAccessible, expectNoCspViolations, expectNoHorizontalScroll, test, viewports } from "./support";

test.describe("chart kit", () => {
  test.beforeEach(async ({ page, origin }) => {
    await page.goto(`${origin}/admin/?kit=charts`);
    await expect(page.getByRole("heading", { level: 1, name: "Chart kit" })).toBeVisible();
  });

  test("a time series draws a path, at most six date ticks and an accessible summary", async ({ page }) => {
    const chart = page.getByRole("img", { name: /^Daily tokens:/ });
    await expect(chart).toHaveAccessibleName(/Oct 1.*Oct 30.*total 1\.\dM.*peak/);
    const path = page.locator('[data-chart="daily"] path[data-series="tokens"]');
    expect(await path.getAttribute("d")).toMatch(/^M[\d.]+ [\d.]+L/);
    const ticks = page.locator('[data-chart="daily"] [data-testid="x-tick"]');
    expect(await ticks.count()).toBeGreaterThanOrEqual(3);
    expect(await ticks.count()).toBeLessThanOrEqual(6);
    await expect(ticks.first()).toHaveText("Oct 1");
  });

  test("the same data is a readable table for screen readers", async ({ page }) => {
    const table = page.getByRole("table", { name: "Daily tokens data" });
    await expect(table.locator("tbody tr")).toHaveCount(30);
    await expect(table.locator("tbody tr").first()).toContainText("Oct 1");
  });

  test("arrow keys move the crosshair and announce each value politely", async ({ page }) => {
    const group = page.getByRole("group", { name: /^Daily tokens chart/ });
    const live = page.locator('[data-chart="daily"] [aria-live="polite"]');
    await group.focus();
    await page.keyboard.press("ArrowRight");
    await expect(live).toContainText("Oct 1");
    await expect(page.locator('[data-chart="daily"] [data-testid="crosshair"]')).toHaveCount(1); // a 0-width line has no box to be "visible"
    await page.keyboard.press("ArrowRight");
    await expect(live).toContainText("Oct 2");
    await page.keyboard.press("ArrowLeft");
    await expect(live).toContainText("Oct 1");
    await page.keyboard.press("End");
    await expect(live).toContainText("Oct 30");
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-chart="daily"] [data-testid="crosshair"]')).toHaveCount(0);
  });

  test("bars rank models with value labels and a legend marks every segment", async ({ page }) => {
    const bars = page.locator('[data-chart="ranked"]');
    await expect(bars.getByTestId("bar-label").first()).toHaveText("gpt-4o");
    await expect(bars.getByTestId("bar-value").first()).toHaveText("1.2M");
    const order = await bars.locator('[data-testid="bar-label"]').allInnerTexts();
    expect(order).toEqual(["gpt-4o", "claude-3-5-sonnet", "gpt-4o-mini"]);
    const shares = page.locator('[data-chart="share"]');
    await expect(shares.getByRole("list", { name: "Legend" }).getByRole("listitem")).toHaveCount(3);
  });

  test("a donut keeps six segments and folds the rest into Other", async ({ page }) => {
    const donut = page.locator('[data-chart="donut"]');
    await expect(donut.getByRole("list", { name: "Legend" }).getByRole("listitem")).toHaveCount(7);
    await expect(donut.getByRole("list", { name: "Legend" })).toContainText("Other");
    expect(await donut.locator("circle[data-segment], path[data-segment]").count()).toBe(7);
  });

  test("a sparkline is an image with a label and loading, empty and error states exist", async ({ page }) => {
    await expect(page.getByRole("img", { name: "Tokens trend, last value 98K" })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loading Daily cost" })).toBeVisible();
    await expect(page.getByText("No usage in this period")).toBeVisible();
    await expect(page.getByRole("alert").filter({ hasText: "Could not load cost" })).toBeVisible();
  });

  test("resizing from desktop to phone re-renders within the container", async ({ page }) => {
    const svg = page.locator('[data-chart="daily"] svg').first();
    const wide = (await svg.boundingBox())!.width;
    await page.setViewportSize(viewports.mobile);
    await expect.poll(async () => (await svg.boundingBox())!.width).toBeLessThan(wide);
    expect((await svg.boundingBox())!.width).toBeLessThanOrEqual(375);
    await expectNoHorizontalScroll(page);
    expect((await svg.boundingBox())!.height).toBeGreaterThanOrEqual(160);
  });

  test("passes axe at every viewport and violates no CSP", async ({ page, csp }) => {
    for (const viewport of Object.values(viewports)) {
      await page.setViewportSize(viewport);
      await expectAccessible(page);
    }
    expectNoCspViolations(csp);
  });
});