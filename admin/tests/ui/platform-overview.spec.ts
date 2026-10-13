import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { GOOD_CODE, OWNER, installPlatform, newWorld } from "./platformSupport";

async function openOverview(page: Page, adminUrl: string, world = newWorld(), path = "platform") {
  world.mfa.verified = true;
  const backend = await installPlatform(page, world);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
  return backend;
}

test.describe("platform overview", () => {
  test("KPIs, top companies, model share, key pool health and recent activity", async ({ page, adminUrl }) => {
    await openOverview(page, adminUrl);
    const kpis = page.getByRole("region", { name: "Key figures" });
    await expect(kpis.getByText("Companies")).toBeVisible();
    await expect(kpis.getByText("1 active")).toBeVisible();
    await expect(kpis.getByText("1 suspended")).toBeVisible();
    await expect(kpis.getByText("Active people")).toBeVisible();
    await expect(kpis).toContainText(/Active people\s*3/);
    await expect(kpis.getByText("Tokens")).toBeVisible();
    await expect(kpis.getByText("2K")).toBeVisible();
    await expect(kpis.getByText("$0.042")).toBeVisible();
    await expect(page.getByRole("figure").filter({ hasText: "Top companies by cost" }).getByTestId("bar-label").filter({ hasText: "Acme Corp" })).toBeVisible();
    await expect(page.getByRole("figure").filter({ hasText: "Tokens by model" }).getByTestId("bar-label").filter({ hasText: "gpt-4o" })).toBeVisible();
    const pool = page.getByRole("region", { name: "Gateway key pool" });
    await expect(pool.getByText("1 active")).toBeVisible();
    await expect(page.getByRole("region", { name: "Recent activity" }).getByText("Company suspended")).toBeVisible();
  });

  test("the per-day series draws tokens and cost over the range with an accessible table", async ({ page, adminUrl }) => {
    const { requests } = await openOverview(page, adminUrl);
    const tokens = page.getByRole("figure").filter({ hasText: "Tokens per day" });
    await expect(tokens).toBeVisible();
    await expect(tokens.getByRole("img")).toBeVisible();
    await expect(tokens.getByRole("table")).toContainText("1.2K"); // 700 prompt + 500 completion on the last day
    await expect(page.getByRole("figure").filter({ hasText: "Cost per day" })).toBeVisible();
    expect(requests.some((request) => request.path.endsWith("/usage/days"))).toBe(true);
  });

  test("a range without usage draws no series and says so", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.usage.days = { days: [{ day: "2026-10-12", requests: 0, prompt_tokens: 0, completion_tokens: 0, estimated_requests: 0, error_requests: 0, cost_micros: 0, unpriced_requests: 0, active_users: 0 }] };
    await openOverview(page, adminUrl, world);
    await expect(page.getByRole("figure").filter({ hasText: "Tokens per day" }).getByText("No usage yet")).toBeVisible();
  });

  test("the range is in the URL, drives the request and survives a reload", async ({ page, adminUrl }) => {
    const { requests } = await openOverview(page, adminUrl);
    await page.getByRole("button", { name: "90 days" }).click();
    await expect(page).toHaveURL(/days=90/);
    const ninety = () =>
      requests
        .filter((request) => request.path.endsWith("/overview") || request.path.endsWith("/usage/days"))
        .map((request) => new URLSearchParams(request.search))
        .filter((params) => (Date.parse(params.get("to")!) - Date.parse(params.get("from")!)) / 86_400_000 === 89);
    await expect.poll(() => ninety().length).toBeGreaterThanOrEqual(2); // the overview (it carries the previous period itself) and the daily series
    await page.reload();
    await page.getByLabel("Email").fill(OWNER.email);
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("button", { name: "90 days" })).toHaveAttribute("aria-pressed", "true");
  });

  test("a fresh platform invites the owner to create the first company", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.companies = [];
    world.usage = { ...world.usage, companies: { companies: [], next_after: null }, models: { models: [], next_after: null }, days: { days: [] } };
    await openOverview(page, adminUrl, world);
    await expect(page.getByRole("heading", { name: "Create your first company" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create company" })).toHaveAttribute("href", "/admin/platform/companies/new");
  });

  test("one failing section says so and can retry without taking the page down", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.failOnce["GET /usage/companies"] = { status: 503, code: "SERVICE_UNAVAILABLE", times: 2 }; // the query client retries a 5xx once
    await openOverview(page, adminUrl, world);
    const figure = page.getByRole("figure").filter({ hasText: "Top companies by cost" });
    await expect(figure.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("region", { name: "Key figures" }).getByText("2K")).toBeVisible();
    await figure.getByRole("button", { name: "Try again" }).click();
    await expect(figure.getByTestId("bar-label").filter({ hasText: "Acme Corp" })).toBeVisible();
  });

  test("a stale second factor sends the owner to the code step and back to the same URL", async ({ page, adminUrl }) => {
    const { world } = await openOverview(page, adminUrl);
    world.mfa.verified = false; // the server no longer trusts this session's verification
    await page.getByRole("button", { name: "7 days" }).click();
    await expect(page.getByRole("heading", { name: "Verify it is you" })).toBeVisible();
    await page.getByLabel("6-digit code").fill(GOOD_CODE);
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
    await expect(page).toHaveURL(/days=7/);
    await expect(page.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true");
  });

  test("is accessible in light and dark on every viewport", async ({ page, adminUrl }) => {
    await openOverview(page, adminUrl);
    await expect(page.getByRole("region", { name: "Key figures" }).getByText("2K")).toBeVisible();
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
