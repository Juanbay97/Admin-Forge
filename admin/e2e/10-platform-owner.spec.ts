import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { OWNER_EMAIL, ownerLinkFile, passCodeStep, readOwner, shot, signInOwner, writeOwner } from "./support/stack";
import { totpCode } from "./support/totp";

// The platform owner's first hour on the real stack: the bootstrap link, the first password, mandatory TOTP enrollment, recovery
// codes, and signing in again with a code. Later journeys reuse the owner this file creates (state kept in the private workspace).
test.describe.configure({ mode: "serial" });
// The platform allows eight live sessions per account: leave none behind, so the journeys can sign in as often as they need.
test.afterEach(async ({ page }) => {
  await page.keyboard.press("Escape").catch(() => undefined); // an open dialog would intercept the click
  const signOut = page.getByRole("button", { name: "Sign out" });
  if (await signOut.isVisible().catch(() => false)) await signOut.click({ timeout: 10_000 });
});

const PASSWORD = "owner-password-for-e2e-2026";

test("the bootstrap link sets the first password and leaves no secret in the address bar", async ({ page }) => {
  const link = readFileSync(ownerLinkFile(), "utf8").trim();
  expect(link).toMatch(/^http:\/\/127\.0\.0\.1:3410\/reset-password#capability=[A-Za-z0-9_-]{43}$/);
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Set your password" })).toBeVisible();
  expect(page.url()).not.toContain("capability");
  expect(new URL(page.url()).pathname).toBe("/admin/reset-password");
  await shot(page, "console", "01-set-password");
  await page.getByLabel("New password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByRole("heading", { name: "Password set" })).toBeVisible();
  // One-time: the same link is spent.
  await page.goto(link);
  await page.getByLabel("New password", { exact: true }).fill(PASSWORD + "-again");
  await page.getByLabel("Confirm password").fill(PASSWORD + "-again");
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByRole("alert")).toContainText("no longer valid");
});

test("the owner is forced through TOTP enrollment and gets recovery codes once", async ({ page }) => {
  await page.goto("/admin/platform");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Protect the console" })).toBeVisible();
  await shot(page, "console", "02-enroll-intro");
  await page.getByRole("button", { name: "Start setup" }).click();
  await expect(page.getByRole("img", { name: /QR code/ })).toBeVisible();
  const secret = ((await page.locator("code").first().textContent()) ?? "").trim();
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);
  await shot(page, "console", "03-enroll-qr");
  await page.getByLabel("6-digit code").fill("000000");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByRole("alert")).toContainText("That code was not accepted");
  const step = Math.floor(Date.now() / 30000);
  await page.getByLabel("6-digit code").fill(totpCode(secret));
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByRole("heading", { name: "Save your recovery codes" })).toBeVisible();
  const recoveryCodes = (await page.getByRole("list", { name: "Recovery codes" }).getByRole("listitem").allTextContents()).map((text) => text.trim());
  expect(recoveryCodes.length).toBeGreaterThanOrEqual(8);
  await shot(page, "console", "04-recovery-codes");
  await expect(page.getByRole("button", { name: "Continue to the console" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /I stored them/ }).check();
  await page.getByRole("button", { name: "Continue to the console" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
  expect(await page.content()).not.toContain(secret);
  writeOwner({ password: PASSWORD, secret, lastStep: step, recoveryCodes });
  await shot(page, "console", "05-overview-first-sign-in");
});

test("signing in again asks for a code, rejects a wrong one and accepts the next step", async ({ page }) => {
  const owner = readOwner();
  await page.goto("/admin/platform");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(owner.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Verify it is you" })).toBeVisible();
  await shot(page, "console", "06-code-step");
  await page.getByLabel("6-digit code").fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("alert")).toContainText("That code was not accepted");
  await passCodeStep(page);
  await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
  // Replay guard: a code step already spent is refused on the next sign-in.
  await page.getByRole("button", { name: "Sign out" }).click();
  await signInOwner(page);
});

test("an organization administrator cannot open the platform console", async ({ page }) => {
  const credentials = JSON.parse(readFileSync(process.env.FORGE_E2E_CREDENTIALS!, "utf8")) as { organizations: Array<{ slug: string; accounts: Array<{ email: string; role: string; password: string }> }> };
  const admin = credentials.organizations.find((item) => item.slug === "org-a")!.accounts.find((account) => account.role === "organization_admin")!;
  await page.goto("/admin/platform");
  await page.getByLabel("Email").fill(admin.email);
  await page.getByLabel("Password").fill(admin.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
});
