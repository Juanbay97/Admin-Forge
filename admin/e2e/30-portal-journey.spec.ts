import { createHash } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { ensureCatalogue, meteredChat, tokenFor } from "./support/api";
import { mailTo, readCompany, shot } from "./support/stack";

// The invitation-to-usage journey on the real stack. The company comes from 20-platform-console (the wizard created it and mailed its
// first administrator); everything here is what that administrator and the people they invite actually do.
test.describe.configure({ mode: "serial" });

const ADMIN_PASSWORD = "initech-admin-password-2026";
const MEMBER = { email: "nina@e2e-initech.test", name: "Nina Newhire", password: "nina-member-password-2026" };

async function join(page: Page, link: string, email: string, password: string) {
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");
  await page.getByLabel("Your email").fill(email);
  await page.getByLabel("New password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
}

async function signIn(page: Page, email: string, password: string, path: string) {
  await page.goto(path);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.afterEach(async ({ page }) => {
  await page.keyboard.press("Escape").catch(() => undefined);
  const out = page.getByRole("button", { name: "Sign out" });
  if (await out.isVisible().catch(() => false)) await out.click({ timeout: 10_000 });
});

test("the first administrator joins from the mailed link on the branded page and lands on the download page", async ({ page, request }) => {
  const company = readCompany();
  const mail = mailTo(company.adminEmail);
  expect(mail.subject).toMatch(/invitation/i);
  await join(page, mail.link, company.adminEmail, ADMIN_PASSWORD);
  await expect(page.getByText("Initech Platform").first()).toBeVisible(); // the branding the owner saved, before anyone signed in
  await shot(page, "portal", "01-join-branded");
  await page.getByRole("button", { name: "Create password and continue" }).click();
  await expect(page).toHaveURL(/\/admin\/portal\/download/);
  await expect(page.getByTestId("company-code")).toHaveText(company.slug);
  await expect(page.getByRole("link", { name: "Download for Windows" })).toHaveAttribute("href", "/downloads/Forge-Setup-0.0.0-local.exe");
  await shot(page, "portal", "02-download");

  // The installer is really served, and its hash is the one the page shows.
  const manifest = (await (await request.get("/downloads/latest.json")).json()) as { platforms: { windows: { url: string; sha256: string } } };
  const file = await request.get(manifest.platforms.windows.url);
  expect(file.ok()).toBe(true);
  expect(createHash("sha256").update(await file.body()).digest("hex")).toBe(manifest.platforms.windows.sha256);
  expect((await request.get("/downloads/%2e%2e/secret.txt")).status()).toBe(404);
  await page.getByText("Verify the download").click();
  await expect(page.getByTestId("sha256")).toHaveText(manifest.platforms.windows.sha256);
  // The invitation is single-use: the same link no longer works.
  await join(page, mail.link, company.adminEmail, ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Create password and continue" }).click();
  await expect(page.getByRole("heading", { name: "This invitation can no longer be used" })).toBeVisible();
  await shot(page, "portal", "03-link-used");
});

test("the administrator invites a person from the Members page and the invitation arrives with a branded link", async ({ page }) => {
  const company = readCompany();
  await signIn(page, company.adminEmail, ADMIN_PASSWORD, "/admin/company/members");
  await expect(page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
  await page.getByRole("button", { name: "Invite member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(MEMBER.name);
  await dialog.getByLabel("Email").fill(MEMBER.email);
  const choices = await dialog.getByLabel("Department").locator("option").evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value).filter(Boolean));
  await dialog.getByLabel("Department").selectOption(choices[0]!);
  await dialog.getByRole("button", { name: /Send invitation|Invite/ }).last().click();
  await expect(page.getByText(`Invitation sent to ${MEMBER.email}.`)).toBeVisible();
  await page.getByRole("tab", { name: "Departments" }).click();
  await expect(page.getByRole("list", { name: "Departments" }).getByRole("listitem").first()).toBeVisible();
  await page.getByLabel("New department").fill("Support");
  await page.getByRole("button", { name: "Create department" }).click();
  await expect(page.getByRole("list", { name: "Departments" }).getByText("Support")).toBeVisible();
  await shot(page, "portal", "10-members-departments");
  // An invitation issued by an administrator carries no company-code hint (only the platform owner's first-admin invitation does), so
  // the join page for this person is the Prometheon default until they sign in; the download page then shows the company code.
  expect(mailTo(MEMBER.email).link).toMatch(/\/onboarding#invitation_id=[0-9a-f-]{36}&capability=[A-Za-z0-9_-]{43}$/);
  void company;
});

test("the person joins, downloads and finds their own usage page", async ({ page }) => {
  const company = readCompany();
  const mail = mailTo(MEMBER.email);
  await join(page, mail.link, MEMBER.email, MEMBER.password);
  await page.getByRole("button", { name: "Create password and continue" }).click();
  await expect(page).toHaveURL(/\/admin\/portal\/download/);
  await expect(page.getByTestId("company-code")).toHaveText(company.slug);
  await expect(page.getByRole("link", { name: "Open Forge" })).toHaveAttribute("href", /^prometheon-forge:\/\/join\?cp=http%3A%2F%2F127\.0\.0\.1%3A3410&code=e2e-initech$/);
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Home" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Welcome, Nina" })).toBeVisible();
  await shot(page, "portal", "20-member-home");
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "My usage" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "My usage" })).toBeVisible();
  await expect(page.getByText("No usage yet")).toBeVisible(); // the live own-usage route answers zeros before the first conversation
  await shot(page, "portal", "21-my-usage");
  // A plain member has no way into the company area.
  await page.goto("/admin/company/members");
  await page.getByLabel("Email").fill(MEMBER.email);
  await page.getByLabel("Password").fill(MEMBER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
});

test("the administrator's dashboard shows that person's real usage", async ({ page, request }) => {
  const company = readCompany();
  const adminToken = await tokenFor(request, { email: company.adminEmail, role: "organization_admin", password: ADMIN_PASSWORD });
  const alias = await ensureCatalogue(request, company.id, adminToken);
  await meteredChat(request, company.id, await tokenFor(request, { email: MEMBER.email, role: "member", password: MEMBER.password }), alias);

  await signIn(page, company.adminEmail, ADMIN_PASSWORD, "/admin/company");
  const usage = page.getByRole("region", { name: "Usage" });
  await expect(usage.getByRole("heading", { name: "Usage" })).toBeVisible();
  const row = usage.getByRole("table", { name: "People", exact: true }).getByRole("row", { name: new RegExp(MEMBER.name) });
  await expect(row).toBeVisible();
  await expect(row.getByText("Support").or(row.getByText("General"))).toBeVisible();
  await expect(usage.getByRole("region", { name: "Key figures" }).getByText(/^1 of \d+$/)).toBeVisible();
  await shot(page, "portal", "30-company-dashboard");
  // The administrator moves the person to the Support department (the live assignment route) and the list shows it.
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Members" }).click();
  const people = page.getByRole("table", { name: "Members" });
  await people.getByRole("row", { name: new RegExp(MEMBER.name) }).getByRole("button", { name: /Change department/ }).click();
  const move = page.getByRole("dialog", { name: "Change department" });
  await move.getByLabel("Department").selectOption({ label: "Support" });
  await move.getByRole("button", { name: "Save department" }).click();
  await expect(move).toBeHidden();
  await expect(people.getByRole("row", { name: new RegExp(MEMBER.name) })).toContainText("Support");
  await shot(page, "portal", "32-department-assigned");
  // The Gateway page is read-only: no key can be entered by a company administrator.
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Gateway" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Gateway" })).toBeVisible();
  await expect(page.locator("input[type=password]")).toHaveCount(0);
  await shot(page, "portal", "31-gateway-read-only");
});

test("the person's own usage page now shows the metered conversation", async ({ page }) => {
  await signIn(page, MEMBER.email, MEMBER.password, "/admin/portal/usage");
  const mine = page.getByRole("region", { name: "My usage" });
  await expect(mine.getByText("Requests")).toBeVisible();
  await expect(mine.getByText("1", { exact: true })).toBeVisible();
  await expect(page.getByText("No usage yet")).toHaveCount(0);
  await shot(page, "portal", "40-my-usage-metered");
});