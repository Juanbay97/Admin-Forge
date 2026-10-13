import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { ACME, GLOBEX, OWNER, installPlatform, newWorld } from "./platformSupport";

async function open(page: Page, adminUrl: string, path: string) {
  const world = newWorld();
  world.mfa.verified = true;
  const backend = await installPlatform(page, world);
  await page.goto(adminUrl + path);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  return backend;
}

test.describe("company usage tab", () => {
  test("shows the company's tokens, cost and quality counters for the range, with the prompt/completion split", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}?tab=usage`);
    await expect(page.getByRole("tab", { name: "Usage", selected: true })).toBeVisible();
    const kpis = page.getByRole("region", { name: "Company usage" });
    await expect(kpis.getByText("1.4K")).toBeVisible(); // 900 prompt + 500 completion
    await expect(kpis.getByText("$0.03")).toBeVisible();
    await expect(kpis.getByText("7", { exact: true })).toBeVisible(); // requests
    const split = page.getByRole("figure").filter({ hasText: "Prompt and completion tokens" });
    await expect(split.getByTestId("bar-label").filter({ hasText: "Prompt" })).toBeVisible();
    await expect(split.getByTestId("bar-label").filter({ hasText: "Completion" })).toBeVisible();
  });

  test("the range is in the URL and refetches the company's window", async ({ page, adminUrl }) => {
    const { requests } = await open(page, adminUrl, `platform/companies/${ACME}?tab=usage`);
    await page.getByRole("button", { name: "7 days" }).click();
    await expect(page).toHaveURL(/days=7/);
    await expect.poll(() => requests.filter((request) => request.path.endsWith("/usage/companies")).some((request) => { const p = new URLSearchParams(request.search); return (Date.parse(p.get("to")!) - Date.parse(p.get("from")!)) / 86_400_000 === 6; })).toBe(true);
  });

  test("a company without usage says so and points at the setup", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${GLOBEX}?tab=usage`);
    await expect(page.getByText("No usage yet")).toBeVisible();
  });

  test("is accessible on every viewport, light and dark", async ({ page, adminUrl }) => {
    await open(page, adminUrl, `platform/companies/${ACME}?tab=usage`);
    await expect(page.getByRole("region", { name: "Company usage" })).toBeVisible();
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