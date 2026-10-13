import type { Page } from "@playwright/test";
import { expect, expectAccessible, expectNoHorizontalScroll, test, viewports } from "./support";
import { GOOD_CODE, OWNER, RECOVERY, installPlatform, newWorld } from "./platformSupport";

const SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";

async function signIn(page: Page, adminUrl: string) {
  await page.goto(adminUrl);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.describe("platform sign-in challenge", () => {
  test("an enrolled owner must pass the code step before any platform data is requested", async ({ page, adminUrl }) => {
    const { requests } = await installPlatform(page);
    await signIn(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Verify it is you" })).toBeVisible();
    const code = page.getByLabel("6-digit code");
    await expect(code).toHaveAttribute("autocomplete", "one-time-code");
    await expect(code).toHaveAttribute("inputmode", "numeric");
    await code.fill("000000");
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByRole("alert")).toContainText("That code was not accepted");
    await expect(code).toBeFocused();
    expect(requests.filter((request) => /\/(companies|usage|audit|gateway-keys|prices)/.test(request.path))).toEqual([]);
    await code.fill(GOOD_CODE);
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
  });

  test("a recovery code is the alternative", async ({ page, adminUrl }) => {
    await installPlatform(page);
    await signIn(page, adminUrl);
    await page.getByRole("button", { name: "Use a recovery code" }).click();
    await page.getByLabel("Recovery code").fill(RECOVERY);
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
  });

  test("after the server lockout the form is disabled and says when to retry", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.failOnce["POST /login/mfa"] = { status: 429, code: "MFA_LOCKED" };
    await installPlatform(page, world);
    await signIn(page, adminUrl);
    await page.getByLabel("6-digit code").fill(GOOD_CODE);
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByRole("alert")).toContainText("Try again in 15 minutes");
    await expect(page.getByLabel("6-digit code")).toBeDisabled();
    await expect(page.getByRole("button", { name: "Verify" })).toBeDisabled();
  });

  test("the challenge is accessible on every viewport, light and dark", async ({ page, adminUrl }) => {
    await installPlatform(page);
    await signIn(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Verify it is you" })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});

test.describe("platform TOTP enrollment", () => {
  test("QR, manual secret, confirm with a code, recovery codes once, nothing secret left afterwards", async ({ page, adminUrl, context }) => {
    const world = newWorld();
    world.mfa = { state: "none", verified: false };
    const { requests } = await installPlatform(page, world);
    await signIn(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Protect the console" })).toBeVisible();
    await page.getByRole("button", { name: "Start setup" }).click();
    await expect(page.getByRole("img", { name: /QR code/ })).toBeVisible();
    await expect(page.getByText(SECRET)).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy secret" })).toBeVisible();
    expect(page.url()).not.toContain(SECRET);
    await page.getByLabel("6-digit code").fill("000000");
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("alert")).toContainText("That code was not accepted");
    await page.getByLabel("6-digit code").fill(GOOD_CODE);
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("heading", { name: "Save your recovery codes" })).toBeVisible();
    await expect(page.getByText("aaaa-bbbb-cccc")).toBeVisible();
    await expect(page.getByText(SECRET)).toHaveCount(0);
    const proceed = page.getByRole("button", { name: "Continue to the console" });
    await expect(proceed).toBeDisabled();
    expect(requests.filter((request) => /\/(companies|usage|audit)/.test(request.path))).toEqual([]);
    await page.getByRole("checkbox", { name: /I stored them/ }).check();
    await proceed.click();
    await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
    const html = await page.content();
    expect(html).not.toContain(SECRET);
    expect(html).not.toContain("aaaa-bbbb-cccc");
    const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
    expect(storage).not.toContain(SECRET);
    expect(storage).not.toContain("aaaa-bbbb-cccc");
    expect(await context.cookies()).toEqual([]);
  });

  test("recovery codes can be downloaded without a CSP violation", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.mfa = { state: "none", verified: false };
    await installPlatform(page, world);
    await signIn(page, adminUrl);
    await page.getByRole("button", { name: "Start setup" }).click();
    await page.getByLabel("6-digit code").fill(GOOD_CODE);
    await page.getByRole("button", { name: "Confirm" }).click();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download" }).click();
    expect((await download).suggestedFilename()).toBe("forge-recovery-codes.txt");
  });

  test("an unconfirmed enrollment found on reload offers a code step and a fresh start", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.mfa = { state: "pending", verified: false };
    await installPlatform(page, world);
    await signIn(page, adminUrl);
    await expect(page.getByRole("heading", { name: "Verify it is you" })).toBeVisible();
    await page.getByRole("button", { name: "Start setup again" }).click();
    await expect(page.getByRole("button", { name: "Start setup" })).toBeVisible();
  });

  test("enrollment is accessible on every viewport", async ({ page, adminUrl }) => {
    const world = newWorld();
    world.mfa = { state: "none", verified: false };
    await installPlatform(page, world);
    await signIn(page, adminUrl);
    await page.getByRole("button", { name: "Start setup" }).click();
    await expect(page.getByRole("img", { name: /QR code/ })).toBeVisible();
    for (const size of Object.values(viewports)) {
      await page.setViewportSize(size);
      await expectNoHorizontalScroll(page);
      await expectAccessible(page);
    }
  });
});
