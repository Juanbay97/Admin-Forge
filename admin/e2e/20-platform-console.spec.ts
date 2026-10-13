import { expect, test } from "@playwright/test";
import { ensureCatalogue, meteredChat, seededOrg, tokenFor } from "./support/api";
import { mailTo, readCompany, shot, signInOwner, writeCompany } from "./support/stack";

// The platform console against the real stack, after 10-platform-owner created the owner. Each journey signs in with a password
// and the next TOTP step; usage comes from real metered chats through the fake gateway.
test.describe.configure({ mode: "serial" });
// The platform allows eight live sessions per account: leave none behind, so the journeys can sign in as often as they need.
test.afterEach(async ({ page }) => {
  await page.keyboard.press("Escape").catch(() => undefined); // an open dialog would intercept the click
  const signOut = page.getByRole("button", { name: "Sign out" });
  if (await signOut.isVisible().catch(() => false)) await signOut.click({ timeout: 10_000 });
});

test("the overview shows real metered usage, the key pool and the audit trail", async ({ page, request }) => {
  // org-b carries the metered traffic: the older journeys (admin-flow) publish and inspect org-a's catalogue themselves.
  const orgA = seededOrg("org-b");
  const alias = await ensureCatalogue(request, orgA.id, await tokenFor(request, orgA.admin));
  await meteredChat(request, orgA.id, await tokenFor(request, orgA.member), alias);

  await signInOwner(page);
  await expect(page.getByRole("heading", { level: 1, name: "Platform overview" })).toBeVisible();
  const kpis = page.getByRole("region", { name: "Key figures" });
  await expect(kpis.getByText("Companies")).toBeVisible();
  await expect(page.getByRole("figure").filter({ hasText: "Top companies by cost" }).getByTestId("bar-label").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Gateway key pool" }).getByText(/active/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Recent activity" }).getByText("Second factor enrolled")).toBeVisible();
  await shot(page, "console", "10-overview");
  await page.getByRole("button", { name: "7 days" }).click();
  await expect(page).toHaveURL(/days=7/);
  await expect(page.getByRole("figure").filter({ hasText: "Tokens by model" }).getByTestId("bar-label").first()).toBeVisible();
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await shot(page, "console", "11-overview-dark");
});

test("companies are listed, searched, opened and suspended with the typed code, and reactivated", async ({ page, request }) => {
  const orgB = seededOrg("org-b");
  await signInOwner(page, "/admin/platform/companies");
  const table = page.getByRole("table", { name: "Companies" });
  await expect(table.getByRole("link", { name: "Organization A" })).toBeVisible();
  await expect(table.getByRole("link", { name: "Organization B" })).toBeVisible();
  await shot(page, "console", "20-companies");
  await page.getByLabel("Search companies").fill("organization b");
  await expect(page).toHaveURL(/q=organization/);
  await expect(table.getByRole("link", { name: "Organization A" })).toHaveCount(0);
  await table.getByRole("link", { name: "Organization B" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Organization B" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Setup" }).getByText("Gateway keys")).toBeVisible();
  await shot(page, "console", "21-company-detail");

  await page.getByRole("button", { name: "Suspend company" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByRole("button", { name: "Suspend" })).toBeDisabled();
  await shot(page, "console", "22-suspend-confirm");
  await dialog.getByLabel(/Type .* to confirm/).fill("org-b");
  await dialog.getByRole("button", { name: "Suspend" }).click();
  await expect(page.getByText("This company is suspended")).toBeVisible();
  const denied = await request.post("/forge/v1/accounts/login", { data: { email: orgB.admin.email, password: orgB.admin.password } });
  const token = denied.ok() ? ((await denied.json()) as { access_token: string }).access_token : null;
  const me = token ? await request.get("/forge/v1/accounts/me", { headers: { Authorization: `Bearer ${token}` } }) : denied;
  expect(me.ok(), "a suspended company's administrator must not get through").toBe(false);

  await page.getByRole("button", { name: "Reactivate company" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reactivate" }).click();
  await expect(page.getByText("This company is suspended")).toHaveCount(0);
  const back = await request.post("/forge/v1/accounts/login", { data: { email: orgB.admin.email, password: orgB.admin.password } });
  expect(back.ok()).toBe(true);
});
test("the wizard creates a company, applies keys and models and mails the first administrator's invitation", async ({ page }) => {
  await signInOwner(page, "/admin/platform/companies/new");
  await expect(page.getByRole("heading", { level: 1, name: "Create a company" })).toBeVisible();
  await page.getByLabel("Company name").fill("E2E Initech");
  await expect(page.getByLabel("Company code")).toHaveValue("e2e-initech");
  await expect(page.getByText("Code is available")).toBeVisible();
  await shot(page, "console", "30-wizard-company");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("checkbox", { name: "Customize branding" }).check();
  await page.getByLabel("Product name").fill("Initech Forge");
  await page.getByLabel("Primary color", { exact: true }).fill("#1D4ED8");
  await shot(page, "console", "31-wizard-branding");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Administrator email").fill("ada@e2e-initech.test");
  await page.getByLabel("Administrator name").fill("Ada Initech");
  await page.getByRole("button", { name: "Next" }).click();
  const keys = page.getByRole("group", { name: "Gateway keys" }).getByRole("checkbox");
  await expect(keys.first()).toBeVisible();
  await keys.first().check();
  await page.getByLabel("Add a model").fill("fake-fast");
  await page.getByRole("button", { name: "Add model" }).click();
  await page.getByLabel("Add a model").fill("fake-slow");
  await page.getByRole("button", { name: "Add model" }).click();
  await shot(page, "console", "32-wizard-keys-models");
  await page.getByRole("button", { name: "Next" }).click();
  await shot(page, "console", "33-wizard-review");
  await page.getByRole("button", { name: "Create company" }).click();
  await expect(page.getByRole("heading", { name: "E2E Initech is ready" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Invitation sent to ada@e2e-initech.test")).toBeVisible();
  await shot(page, "console", "34-wizard-success");
  const mail = mailTo("ada@e2e-initech.test");
  expect(mail.link).toMatch(/\/onboarding\?c=e2e-initech#invitation_id=[0-9a-f-]{36}&capability=[A-Za-z0-9_-]{43}$/);
  const href = (await page.getByRole("link", { name: "Open company" }).getAttribute("href")) ?? "";
  const id = href.split("/").pop()!;
  writeCompany({ id, slug: "e2e-initech", name: "E2E Initech", adminEmail: "ada@e2e-initech.test" });
  await page.getByRole("link", { name: "Open company" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E Initech" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Setup" }).getByText("2 allowed")).toBeVisible();
  await expect(page.getByRole("region", { name: "Setup" }).getByText("1 assigned")).toBeVisible();
  await expect(page.getByText("Finish setup")).toHaveCount(0);
});
test("branding, keys and models tabs apply to the company and the public branding follows", async ({ page, request }) => {
  const company = readCompany();
  await signInOwner(page, `/admin/platform/companies/${company.id}?tab=branding`);
  await expect(page.getByRole("tab", { name: "Branding", selected: true })).toBeVisible();
  await page.getByLabel("Product name").fill("Initech Platform");
  await page.getByRole("button", { name: "Save branding" }).click();
  await expect(page.getByText(/Branding saved \(revision \d+\)/)).toBeVisible();
  await shot(page, "console", "40-company-branding");
  const publicBranding = await request.get(`/forge/v1/branding?org=${company.slug}`);
  expect(publicBranding.ok()).toBe(true);
  expect(((await publicBranding.json()) as { name: string }).name).toBe("Initech Platform");

  await page.getByRole("tab", { name: "Keys" }).click();
  const keys = page.getByRole("list", { name: "Assigned keys" });
  await expect(keys.getByRole("listitem")).toHaveCount(1);
  await expect(keys.getByText(/^••••/)).toBeVisible();
  await shot(page, "console", "41-company-keys");

  await page.getByRole("tab", { name: "Models" }).click();
  await page.getByLabel("Add a model").fill("fake-nousage");
  await page.getByRole("button", { name: "Add model" }).click();
  await page.getByRole("button", { name: "Save models" }).click();
  await expect(page.getByText("Allowed models saved")).toBeVisible();
  await shot(page, "console", "42-company-models");
  await page.getByRole("tab", { name: "Overview" }).click();
  await expect(page.getByRole("region", { name: "Setup" }).getByText("3 allowed")).toBeVisible();
});
test("a company's usage tab shows what its members really consumed", async ({ page }) => {
  const orgA = seededOrg("org-b");
  await signInOwner(page, `/admin/platform/companies/${orgA.id}?tab=usage`);
  const kpis = page.getByRole("region", { name: "Company usage" });
  await expect(kpis.getByText("Requests", { exact: true })).toBeVisible();
  await expect(page.getByRole("figure").filter({ hasText: "Prompt and completion tokens" })).toBeVisible();
  await shot(page, "console", "43-company-usage");
});
test("a company's members tab lists its real people read-only", async ({ page }) => {
  const orgB = seededOrg("org-b");
  await signInOwner(page, `/admin/platform/companies/${orgB.id}?tab=members`);
  const table = page.getByRole("table", { name: "Company members" });
  await expect(table.locator("tbody").getByRole("row").first()).toBeVisible();
  await expect(table.getByText("Administrator")).toBeVisible();
  await expect(table.locator("tbody").getByRole("button")).toHaveCount(0);
  await shot(page, "console", "44-company-members");
});
test("the key pool takes a write-only key and the price list round-trips an edit", async ({ page }) => {
  const SECRET = "sk-e2e-0123456789abcdef-WXYZ";
  await signInOwner(page, "/admin/platform/keys");
  await expect(page.getByRole("heading", { level: 1, name: "Gateway keys" })).toBeVisible();
  await page.getByRole("button", { name: "Add key" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Label").fill("E2E Backup");
  await dialog.getByLabel("API key").fill(SECRET);
  await shot(page, "console", "50-add-key");
  await dialog.getByRole("button", { name: "Add key" }).click();
  const row = page.getByRole("table", { name: "Gateway keys" }).getByRole("row", { name: /E2E Backup/ });
  await expect(row.getByText("••••WXYZ")).toBeVisible();
  expect(await page.content()).not.toContain(SECRET);
  await shot(page, "console", "51-key-pool");
  await row.getByRole("button", { name: "Disable E2E Backup" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Disable key" }).click();
  await expect(row.getByText("Disabled")).toBeVisible();

  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Prices" }).click();
  await page.getByRole("button", { name: "Add price" }).click();
  const price = page.getByRole("dialog");
  await price.getByLabel("Model").fill("fake-fast");
  await price.getByLabel("Input, USD per 1M tokens").fill("1.25");
  await price.getByLabel("Output, USD per 1M tokens").fill("5");
  await price.getByRole("button", { name: "Save price" }).click();
  const priced = page.getByRole("table", { name: "Model prices" }).getByRole("row", { name: /fake-fast/ });
  await expect(priced.getByText("$1.25")).toBeVisible();
  await expect(priced.getByText("$5.00")).toBeVisible();
  await priced.getByRole("button", { name: "Edit fake-fast" }).click();
  await page.getByRole("dialog").getByLabel("Output, USD per 1M tokens").fill("6.5");
  await page.getByRole("dialog").getByRole("button", { name: "Save price" }).click();
  await expect(priced.getByText("$6.50")).toBeVisible();
  await expect(priced.getByText("v2")).toBeVisible();
  await shot(page, "console", "52-prices");
  await priced.getByRole("button", { name: "History fake-fast" }).click();
  await expect(page.getByRole("dialog", { name: /Price history/ }).getByRole("row", { name: /v1/ })).toBeVisible();
});
test("the audit log records the whole journey and the palette jumps to a company", async ({ page }) => {
  await signInOwner(page, "/admin/platform/audit");
  const table = page.getByRole("table", { name: "Audit log" });
  for (const action of ["Second factor enrolled", "Company created", "Company suspended", "Company reactivated", "Branding saved", "Gateway keys assigned", "Model access set", "Gateway key added", "Gateway key enabled or disabled", "Model price set"]) {
    await expect(table.getByRole("row", { name: new RegExp(action) }).first(), action).toBeVisible();
  }
  await shot(page, "console", "60-audit");
  await page.getByLabel("Action").selectOption("company.suspended");
  await expect(page).toHaveURL(/action=company.suspended/);
  await expect(table.getByRole("row", { name: /Company created/ })).toHaveCount(0);
  await expect(table.getByRole("row", { name: /Organization B/ })).toBeVisible();

  await page.waitForLoadState("networkidle");
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await palette.getByRole("combobox").fill("e2e-initech");
  await shot(page, "console", "61-palette");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "E2E Initech" })).toBeVisible();
});