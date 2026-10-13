import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { installPlatform } from "./platformSupport";

const CAP = "A".repeat(43);

test.describe("set-password link", () => {
  test("the capability leaves the address bar, the password is set once and nothing is stored", async ({ page, adminUrl, context }) => {
    const { requests } = await installPlatform(page);
    await page.goto(`${adminUrl}reset-password#capability=${CAP}`);
    await expect(page.getByRole("heading", { name: "Set your password" })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    expect(page.url()).not.toContain(CAP);
    await page.getByLabel("New password", { exact: true }).fill("a-long-enough-password");
    await page.getByLabel("Confirm password").fill("another-long-password!!");
    await page.getByRole("button", { name: "Set password" }).click();
    await expect(page.getByText("The passwords do not match.")).toBeVisible();
    await page.getByLabel("Confirm password").fill("a-long-enough-password");
    await page.getByRole("button", { name: "Set password" }).click();
    await expect(page.getByRole("heading", { name: "Password set" })).toBeVisible();
    const consume = requests.filter((request) => request.path.endsWith("/password-reset/consume"));
    expect(consume).toHaveLength(1);
    expect(consume[0]?.body).toEqual({ capability: CAP, password: "a-long-enough-password" });
    expect(requests.filter((request) => request.path.includes("/platform/") || request.path.endsWith("/accounts/me"))).toEqual([]);
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain(CAP);
    expect(await context.cookies()).toEqual([]);
    await page.getByRole("button", { name: "Continue to sign in" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("a short password is refused before anything is sent, and a used link says so", async ({ page, adminUrl }) => {
    const { requests } = await installPlatform(page);
    await page.goto(`${adminUrl}reset-password#capability=${"B".repeat(43)}`);
    await page.getByLabel("New password", { exact: true }).fill("too short");
    await page.getByLabel("Confirm password").fill("too short");
    await page.getByRole("button", { name: "Set password" }).click();
    await expect(page.getByText("Use at least 15 characters.")).toBeVisible();
    expect(requests.filter((request) => request.path.endsWith("/consume"))).toEqual([]);
    await page.getByLabel("New password", { exact: true }).fill("a-long-enough-password");
    await page.getByLabel("Confirm password").fill("a-long-enough-password");
    await page.getByRole("button", { name: "Set password" }).click();
    await expect(page.getByRole("alert")).toContainText("no longer valid");
    await expect(page.getByLabel("New password", { exact: true })).toHaveValue("");
  });

  test("a link without its capability cannot be used", async ({ page, adminUrl }) => {
    await installPlatform(page);
    await page.goto(`${adminUrl}reset-password`);
    await expect(page.getByRole("heading", { name: "This link cannot be used" })).toBeVisible();
  });

  test("is accessible and fits every viewport", async ({ page, adminUrl }) => {
    await installPlatform(page);
    await page.goto(`${adminUrl}reset-password#capability=${CAP}`);
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});
