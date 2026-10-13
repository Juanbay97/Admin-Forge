import { expect, test } from "@playwright/test";
import { ensureCatalogue, meteredChat, seededOrg, tokenFor } from "./support/api";
import { mailTo, shot, signInOwner, writeCompany } from "./support/stack";

// The platform console against the real stack, after 10-platform-owner created the owner. Each journey signs in with a password
// and the next TOTP step; usage comes from real metered chats through the fake gateway.
test.describe.configure({ mode: "serial" });

test("the overview shows real metered usage, the key pool and the audit trail", async ({ page, request }) => {
  const orgA = seededOrg("org-a");
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