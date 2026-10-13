import { expect, test } from "@playwright/test";
import { ensureCatalogue, meteredChat, seededOrg, tokenFor } from "./support/api";
import { shot, signInOwner } from "./support/stack";

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