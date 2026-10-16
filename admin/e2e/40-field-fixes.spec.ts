import { expect, test, type Page } from "@playwright/test";
import { meteredChat, releaseTokens, tokenFor } from "./support/api";
import { mailTo, readCompany, shot, signInOwner } from "./support/stack";

// The field fixes on the real stack, after 30-portal-journey created and joined the company: the public landing, the forgot-password
// flow through the real mailbox, the download area for both roles, and the platform owner's model discovery through the fake gateway.
test.describe.configure({ mode: "serial" });
test.afterEach(async ({ request }) => releaseTokens(request));
test.afterEach(async ({ page }) => {
  await page.keyboard.press("Escape").catch(() => undefined);
  const out = page.getByRole("button", { name: "Sign out" });
  if (await out.isVisible().catch(() => false)) await out.click({ timeout: 10_000 });
});

const ADMIN = { password: "initech-admin-password-2026" };
const MEMBER = { email: "nina@e2e-initech.test", password: "nina-member-password-2026", fresh: "nina-new-password-2026-ok" };
const ENTRY = "Download Prometheon Forge";

async function signIn(page: Page, email: string, password: string, path: string) {
  await page.goto(path);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("the domain root is the public landing: brand, sign in, the real installer and the OpenYak credit", async ({ page, request }) => {
  const response = await request.get("/");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-security-policy"]).toContain("default-src 'none'");
  expect(response.headers()["cache-control"]).toBe("no-store");
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("private AI workspace");
  await expect(page.getByRole("main").getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/admin/");
  const section = page.getByRole("region", { name: "Download for Windows" });
  await expect(section.getByRole("link", { name: "Download for Windows" })).toHaveAttribute("href", "/downloads/Forge-Setup-0.0.0-local.exe");
  await expect(section.getByTestId("sha256")).toHaveText(/^[a-f0-9]{64}$/);
  await expect(page.getByRole("contentinfo")).toContainText("OpenYak");
  await shot(page, "portal", "50-landing");
  await page.getByRole("main").getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/admin\/$/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("a short or wrong password gets the one generic message, and a forgotten one is reset through the mailed link", async ({ page }) => {
  await page.goto("/admin/");
  await page.getByLabel("Email").fill(MEMBER.email);
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
  await expect(page.getByLabel("Password")).toHaveValue("");

  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page.getByRole("heading", { name: "Forgot your password?" })).toBeVisible();
  await page.getByLabel("Email").fill("nobody-at-all@e2e-initech.test");
  await page.getByRole("button", { name: "Send reset link" }).click();
  const neutral = await page.getByRole("status").filter({ hasText: "If an account exists" }).textContent();
  await page.goto("/admin/forgot-password");
  await page.getByLabel("Email").fill(MEMBER.email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status").filter({ hasText: "If an account exists" })).toHaveText(neutral ?? "");
  await shot(page, "portal", "51-forgot-password");

  const mail = mailTo(MEMBER.email, /Reset your Forge password/);
  expect(mail.link).toMatch(/\/reset-password#capability=[A-Za-z0-9_-]{43}$/);
  await page.goto(mail.link);
  await expect(page.getByRole("heading", { name: "Set your password" })).toBeVisible();
  expect(page.url()).not.toContain("capability");
  await page.getByLabel("New password", { exact: true }).fill(MEMBER.fresh);
  await page.getByLabel("Confirm password").fill(MEMBER.fresh);
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByRole("heading", { name: "Password set" })).toBeVisible();
  await page.getByRole("button", { name: "Continue to sign in" }).click();
  await page.getByLabel("Email").fill(MEMBER.email);
  await page.getByLabel("Password").fill(MEMBER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
  await page.getByLabel("Password").fill(MEMBER.fresh);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Welcome, Nina/ })).toBeVisible();
  // The link was single-use: it does not work twice.
  await page.goto(mail.link);
  await page.getByLabel("New password", { exact: true }).fill(MEMBER.fresh + "x");
  await page.getByLabel("Confirm password").fill(MEMBER.fresh + "x");
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByRole("alert")).toContainText("no longer valid");
});

test("members and administrators both find Download Prometheon Forge in the navigation and on the dashboard", async ({ page }) => {
  const company = readCompany();
  await signIn(page, MEMBER.email, MEMBER.fresh, "/admin/portal");
  const nav = page.getByRole("navigation", { name: "Sections" });
  await expect(nav.getByRole("button", { name: ENTRY })).toBeVisible();
  const card = page.getByRole("region", { name: ENTRY });
  await expect(card).toContainText("v0.0.0-local");
  await nav.getByRole("button", { name: ENTRY }).click();
  await expect(page.getByRole("main").getByRole("button", { name: ENTRY })).toBeVisible();
  await page.getByText("Advanced", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Download configuration (forge-install.json)" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, company.adminEmail, ADMIN.password, "/admin/company");
  await expect(nav.getByRole("button", { name: ENTRY })).toBeVisible();
  await expect(page.getByRole("region", { name: ENTRY })).toContainText("v0.0.0-local");
  await shot(page, "portal", "52-admin-dashboard-download");
  await nav.getByRole("button", { name: ENTRY }).click();
  await expect(page).toHaveURL(/\/admin\/company\/download$/);
  await expect(page.getByTestId("company-code")).toHaveText(company.slug);
  const stamped = page.waitForEvent("download");
  await page.getByRole("main").getByRole("button", { name: ENTRY }).click();
  expect((await stamped).suggestedFilename()).toBe(`Prometheon-Forge-Setup-${company.slug}.exe`);
  await page.getByText("Advanced", { exact: true }).click();
  const waiting = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download configuration (forge-install.json)" }).click();
  expect((await waiting).suggestedFilename()).toBe("forge-install.json");
  await shot(page, "portal", "53-admin-download-page");
});

test("the platform owner discovers the company's models through its key, selects, aliases and publishes", async ({ page, request }) => {
  const company = readCompany();
  await signInOwner(page, `/admin/platform/companies/${company.id}?tab=models`);
  await expect(page.getByText("Published", { exact: true })).toBeVisible(); // the administrator's earlier publication is preselected below
  await page.getByRole("button", { name: "Discover models" }).click();
  const keys = page.getByRole("list", { name: "Key discovery" });
  await expect(keys.getByRole("listitem").first()).toContainText("Reachable");
  await expect(keys.getByRole("listitem").first()).toContainText("5 models");
  const list = page.getByRole("list", { name: "Discovered models" });
  await expect(list.getByRole("listitem")).toHaveCount(5);
  await expect(page.getByText(/Last discovered: .* UTC/)).toBeVisible();
  await page.getByLabel("Search models").fill("nousage");
  await page.getByLabel("Select fake-nousage").check();
  await page.getByLabel("Alias for fake-nousage").fill("plain");
  await page.getByLabel("Search models").fill("");
  await page.getByLabel("Alias for fake-fast").fill("quick");
  await page.getByLabel("Default model fake-fast").check();
  await shot(page, "console", "70-company-catalog");
  await page.getByRole("button", { name: "Publish catalog" }).click();
  await expect(page.getByText("Catalog published")).toBeVisible();
  await expect(page.getByRole("table", { name: "Allowed models" }).getByRole("row", { name: /fake-nousage/ })).toBeVisible();
  await expect(page.getByRole("table", { name: "Allowed models" }).getByRole("row", { name: /fake-slow/ })).toHaveCount(0);

  // What the company sees and uses is exactly what the owner published.
  const member = await tokenFor(request, { email: MEMBER.email, role: "member", password: MEMBER.fresh });
  const models = await request.get(`/forge/v1/orgs/${company.id}/models`, { headers: { Authorization: `Bearer ${member}` } });
  expect(((await models.json()) as { models: Array<{ id: string }>; default_model: string }).models.map((item) => item.id).sort()).toEqual(["plain", "quick"]);
  await meteredChat(request, company.id, member, "quick");
  // Both actions are in the platform audit log with the company they were about.
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Audit log" }).click();
  const table = page.getByRole("table", { name: "Audit log" });
  await expect(table.getByRole("row", { name: /Catalog published/ }).first()).toBeVisible();
  await expect(table.getByRole("row", { name: /Models discovered/ }).first()).toBeVisible();
});
