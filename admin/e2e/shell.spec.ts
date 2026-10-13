import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Real stack, no mocks: the shell's role redirect, deep links, expiry from a genuinely revoked token and the responsive drawer.
interface Credentials {
  organizations: Array<{ slug: string; organization_id: string; accounts: Array<{ email: string; role: string; password: string }> }>;
}
const file = process.env.FORGE_E2E_CREDENTIALS;
if (!file) throw new Error("FORGE_E2E_CREDENTIALS is not set: run scripts\\admin-e2e.ps1.");
const credentials = JSON.parse(readFileSync(file, "utf-8")) as Credentials;
const orgA = credentials.organizations.find((organization) => organization.slug === "org-a")!;
const admin = orgA.accounts.find((account) => account.role === "organization_admin")!;
const member = orgA.accounts.find((account) => account.role === "member")!;

const pathOf = (page: Page) => new URL(page.url()).pathname;

async function signIn(page: Page, account = admin) {
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("an organization administrator lands on the company area and a deep link survives sign-in", async ({ page }) => {
  await page.goto("/admin/company/members");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  expect(pathOf(page)).toBe("/admin/company/members");
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
  expect(pathOf(page)).toBe("/admin/company/members");
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Overview" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Organization A" })).toBeVisible();
  expect(pathOf(page)).toBe("/admin/company");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("the root sends a signed-in administrator home and a plain member is turned away", async ({ page }) => {
  await page.goto("/admin/");
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1, name: "Organization A" })).toBeVisible();
  expect(pathOf(page)).toBe("/admin/company");
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, member);
  await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
});

test("a token revoked on the server expires the session in place and sign-in resumes on the same URL", async ({ page, request }) => {
  let token = "";
  page.on("request", (candidate) => {
    const header = candidate.headers()["authorization"];
    if (header?.startsWith("Bearer ")) token = header.slice(7);
  });
  await page.goto("/admin/company/gateway");
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1, name: "Gateway" })).toBeVisible();
  expect(token).not.toBe("");
  // Revoke the very token the page holds, through the API, as a sign-out elsewhere would.
  expect((await request.post("/forge/v1/accounts/logout", { headers: { Authorization: `Bearer ${token}` } })).ok()).toBe(true);
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Members" }).click();
  await expect(page.getByText("Your session expired. Sign in again to continue.")).toBeVisible();
  expect(pathOf(page)).toBe("/admin/company/members");
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
});

test("an unregistered area is not found and the phone layout uses a drawer", async ({ page }) => {
  await page.goto("/admin/platform");
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1, name: "Not found" })).toBeVisible();
  await page.goto("/admin/company");
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1, name: "Organization A" })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole("navigation", { name: "Sections" })).toBeHidden();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("dialog", { name: "Navigation" }).getByRole("button", { name: "Catalog" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Catalog" })).toBeVisible();
});